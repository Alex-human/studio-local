"""Mobile companion end-to-end invariants, using an isolated library and synthetic media."""
import concurrent.futures
import copy
import http.client
import json
import sys
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'mobile'))
import server as mobile


class Mobile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='studio-mobile-tests-')
        cls.root = Path(cls.temp.name)
        cls.source = cls.root/'source.mp4'
        mobile.render.run(['-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=30:duration=10',
                           '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=10',
                           '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',cls.source])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.work = self.root/uuid.uuid4().hex
        self.path = self.work/'projects'/'Demo'/'Proyecto.studio'
        self.path.parent.mkdir(parents=True)
        p = mobile.project.new('Prueba móvil',width=160,height=90,fps=30)
        p['assets'] = [dict(id='asset',kind='video',path=str(self.source),name='Sintético',duration=10,width=160,height=90,fps=30,audio=True)]
        p['clips'] = [dict(id='clip',asset='asset',length=240,volumeDb=0,**{'in':30})]
        p['graphics'] = [dict(id='hook',type='title',start=0,length=240,keepTogether=True,props={'text':'Gancho original','size':70})]
        p['audio'] = [dict(id='music',asset='asset',role='music',start=0,length=240,linked=False,volumeDb=-24,**{'in':0})]
        mobile.project.save(self.path,p)
        self.original = copy.deepcopy(p)
        self.app = mobile.Companion(self.work/'projects',self.work/'runtime')
        self.pid = p['id']

    def req(self, **changes):
        return dict(project=self.pid,revision=mobile.project.load(self.path)['revision'],requestId=uuid.uuid4().hex,**changes)

    def edit(self, op, **extra):
        req = self.req(action='edit',op=op)
        req.update(extra)
        return self.app.query(req)

    def test_library_does_not_return_source_paths_or_feedback_snapshots(self):
        self.assertNotIn('path', self.app.query({'action':'library'})['projects'][0])
        d = self.path.parent/'feedback'/'saved'; d.mkdir(parents=True)
        mobile.project.atomic_json(d/'snapshot.studio',self.original)
        self.assertEqual(len(self.app.query({'action':'library'})['projects']),1)
        state = self.app.state(self.pid)
        self.assertNotIn(str(self.source),json.dumps(state))

    def test_text_resize_split_and_free_music_share_canonical_history(self):
        before = self.source.read_bytes()
        self.assertTrue(self.edit({'type':'text','kind':'graphics','id':'hook','text':'Nuevo gancho'})['ok'])
        self.assertTrue(self.edit({'type':'resize','kind':'clips','id':'clip','edge':'end','delta':-30})['ok'])
        p = mobile.project.load(self.path)
        self.assertEqual(mobile.project.duration(p),210)
        self.assertEqual(p['audio'],self.original['audio'])
        self.assertEqual(p['graphics'][0]['length'],210)
        self.assertTrue(self.edit({'type':'resize','kind':'clips','id':'clip','edge':'end','delta':30})['ok'])
        self.assertTrue(self.edit({'type':'splitAt','frame':120})['ok'])
        p = mobile.project.load(self.path)
        self.assertEqual([c['length'] for c in p['clips']],[120,120])
        self.assertEqual(len(p['graphics']),1)
        self.assertEqual(p['graphics'][0]['props']['text'],'Nuevo gancho')
        self.assertEqual(self.source.read_bytes(),before)
        self.assertTrue(self.app.query(self.req(action='undo'))['ok'])
        self.assertEqual(len(mobile.project.load(self.path)['clips']),1)

    def test_duplicate_delivery_applies_cut_once_concurrently_and_after_restart(self):
        req = self.req(action='edit',op={'type':'resize','kind':'clips','id':'clip','edge':'end','delta':-30})
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as workers:
            responses = list(workers.map(lambda _:self.app.query(req),range(4)))
        self.assertTrue(all(x['ok'] for x in responses))
        self.assertEqual(mobile.project.duration(mobile.project.load(self.path)),210)
        restarted = mobile.Companion(self.work/'projects',self.work/'runtime')
        self.assertTrue(restarted.query(req)['ok'])
        self.assertEqual(mobile.project.load(self.path)['revision'],1)
        altered = {**req,'op':{**req['op'],'delta':-15}}
        with self.assertRaises(ValueError): restarted.query(altered)

    def test_crash_after_write_never_replays_mutation(self):
        req = self.req(action='edit',op={'type':'resize','kind':'clips','id':'clip','edge':'end','delta':-30})
        original = self.app.execute
        def fail_after_write(value):
            original(value)
            raise OSError('simulated lost acknowledgement')
        with patch.object(self.app,'execute',side_effect=fail_after_write):
            with self.assertRaises(OSError): self.app.query(req)
        self.assertTrue(self.app.query(req)['uncertain'])
        self.assertEqual(mobile.project.duration(mobile.project.load(self.path)),210)

    def test_desktop_conflict_preserves_both_versions(self):
        req = self.req(action='edit',op={'type':'text','kind':'graphics','id':'hook','text':'Móvil'})
        mobile.editor.dispatch({'action':'ops','project':str(self.path),'revision':0,'ops':[{'op':'set','kind':'graphics','id':'hook','values':{'props':{'text':'Mac','size':70}}}]})
        response = self.app.query(req)
        self.assertTrue(response['conflict'])
        self.assertEqual(mobile.project.load(self.path)['graphics'][0]['props']['text'],'Mac')

    def test_invalid_edits_do_not_touch_project(self):
        before = self.path.read_bytes()
        invalid = [
            {'type':'resize','kind':'clips','id':'clip','edge':'end','delta':600},
            {'type':'linked','kind':'clips','id':'clip','linked':False},
            {'type':'text','kind':'clips','id':'clip','text':'fake'},
            {'type':'splitAt','frame':0},
            {'type':'set','kind':'clips','id':'clip','asset':'/tmp/private'},
        ]
        for op in invalid: self.assertFalse(self.edit(op)['ok'])
        self.assertEqual(self.path.read_bytes(),before)

    def test_feedback_persists_text_drawing_capture_and_anchor_without_edit(self):
        before = self.path.read_bytes()
        req = self.req(action='note',noteId='mobile-note',frame=75,text='Mover el gancho',strokes=[{'tool':'pen','color':'#ffb777','width':.006,'points':[[.1,.2],[.4,.3]]}])
        response = self.app.query(req)
        self.assertTrue(response['ok'],response)
        self.assertEqual(self.path.read_bytes(),before)
        note = response['result']['note']
        self.assertEqual((note['status'],note['capture'],note['frame']),('open','ready',75))
        self.assertNotIn('files',note)
        self.assertTrue((self.path.parent/'feedback'/'mobile-note'/'annotated.png').exists())
        self.edit({'type':'resize','kind':'clips','id':'clip','edge':'start','delta':15})
        self.assertEqual(self.app.state(self.pid)['notes'][0]['currentFrame'],60)
        self.assertTrue(self.app.query(req)['ok'])
        self.assertEqual(len(self.app.state(self.pid)['notes']),1)

    def test_playlist_has_exact_frame_durations_and_segment_renders_are_reused(self):
        data, _ = self.app.playlist(self.pid,0,0)
        manifest = data.decode()
        self.assertIn('#EXTINF:6.000000000,',manifest)
        self.assertIn('#EXTINF:2.000000000,',manifest)
        self.assertIn('#EXT-X-DISCONTINUITY',manifest)
        with self.assertRaises(ValueError): self.app.segment(self.pid,0,2,'mp4')
        data, kind = self.app.segment(self.pid,0,1,'mp4')
        self.assertEqual(kind,'video/mp4')
        out = self.work/'segment.mp4'; out.write_bytes(data)
        raw = mobile.render.run(['-v','error','-i',out,'-map','0:v','-f','rawvideo','-pix_fmt','rgb24','-'])
        self.assertEqual(len(raw),160*90*3*60)
        with patch.object(mobile.render,'render',side_effect=AssertionError('unexpected rerender')):
            self.assertEqual(self.app.segment(self.pid,0,1,'mp4')[0],data)
            ts, kind = self.app.segment(self.pid,0,1,'ts')
            self.assertEqual(kind,'video/mp2t')
            self.assertGreater(len(ts),0)

    def test_feedback_duplicate_id_cannot_overwrite_and_capture_respects_concurrent_version(self):
        req=self.req(action='note',noteId='race',frame=75,text='Móvil',strokes=[])
        original=mobile.editor.dispatch
        def concurrent_capture(value):
            result=original(value)
            if value.get('command')=='capture':
                original({'action':'feedback','project':str(self.path),'command':'update','id':'race',
                          'version':result['version'],'values':{'text':'Cambio del Mac'}})
                return original({'action':'feedback','project':str(self.path),'command':'get','id':'race'})
            return result
        with patch.object(mobile.editor,'dispatch',side_effect=concurrent_capture):
            result=self.app.query(req)
        self.assertTrue(result['conflict'])
        note=self.app.state(self.pid)['notes'][0]
        self.assertEqual(note['text'],'Cambio del Mac')
        req['requestId']=uuid.uuid4().hex
        self.assertTrue(self.app.query(req)['conflict'])
        self.assertEqual(self.app.state(self.pid)['notes'][0]['text'],'Cambio del Mac')

    def test_unchanged_interval_survives_edits_and_cached_media_never_waits_for_render_lock(self):
        p = mobile.project.load(self.path)
        p['graphics'][0]['length'] = 90
        mobile.project.save(self.path, p)
        before_key = self.app.snapshot_key(mobile.project.excerpt(p, 0, 180))
        data, _ = self.app.segment(self.pid, 0, 1, 'mp4')
        self.assertTrue(self.edit({'type':'text','kind':'graphics','id':'hook','text':'Otro gancho'})['ok'])
        p = mobile.project.load(self.path)
        self.assertNotEqual(before_key, self.app.snapshot_key(mobile.project.excerpt(p, 0, 180)))
        with patch.object(mobile.render, 'render', side_effect=AssertionError('unrelated interval rerendered')):
            # Holding the render lock proves cached reads bypass background preparation.
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as worker:
                with self.app.media:
                    result = worker.submit(self.app.segment, self.pid, p['revision'], 1, 'mp4').result(timeout=2)
            self.assertEqual(result[0], data)

    def test_warming_is_bounded_and_new_seek_replaces_queue(self):
        with self.app.warm_lock:
            self.app.warming = True
        self.app.warm(self.pid, 0, 0)
        self.assertEqual([job[2] for job in self.app.warm_jobs], [0, 1])
        self.app.warm(self.pid, 0, 210)
        self.assertEqual([job[2] for job in self.app.warm_jobs], [1])
        with patch.object(self.app, 'segment') as segment:
            self.app.warm_media()
            segment.assert_called_once_with(self.pid, 0, 1, 'ts')
        self.assertFalse(self.app.warming)

    def test_note_image_survives_revision_removed_by_undo_branch(self):
        self.edit({'type':'text','kind':'graphics','id':'hook','text':'Revisión uno'})
        self.assertTrue(self.app.query(self.req(action='note',noteId='permanent',frame=75,text='Aquí',strokes=[]))['ok'])
        image,_=self.app.note_image(self.pid,'permanent')
        self.app.query(self.req(action='undo'))
        self.edit({'type':'text','kind':'graphics','id':'hook','text':'Otra rama'})
        with self.assertRaises(mobile.sync.Conflict): self.app.read(self.pid,1)
        self.assertEqual(self.app.note_image(self.pid,'permanent')[0],image)

    def test_note_create_does_not_adopt_concurrent_version_or_revive_deleted_note(self):
        req=self.req(action='note',noteId='create-race',frame=75,text='Móvil',strokes=[])
        original=mobile.editor.dispatch
        def after_create(value):
            result=original(value)
            if value.get('command')=='create':
                original({'action':'feedback','project':str(self.path),'command':'update','id':'create-race',
                          'version':result['version'],'values':{'text':'Cambio del Mac'}})
            return result
        with patch.object(mobile.editor,'dispatch',side_effect=after_create):
            response=self.app.query(req)
        self.assertTrue(response['conflict'])
        note=self.app.state(self.pid)['notes'][0]
        self.assertEqual(note['text'],'Cambio del Mac')
        original({'action':'feedback','project':str(self.path),'command':'update','id':'create-race',
                  'version':note['version'],'values':{'status':'deleted'}})
        req['requestId']=uuid.uuid4().hex
        self.assertTrue(self.app.query(req)['conflict'])
        self.assertEqual(self.app.state(self.pid)['notes'],[])

    def test_http_host_origin_identity_and_ranges(self):
        server = mobile.serve(self.work/'projects',self.work/'http-runtime',port=0)
        thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        try:
            def request(method,path='/',body=None,**headers):
                c = http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=15)
                c.request(method,path,body=body,headers=headers)
                r=c.getresponse(); result=(r.status,dict(r.headers),r.read()); c.close(); return result
            self.assertEqual(request('GET')[0],200)
            self.assertEqual(request('GET','/icon.png')[0],200)
            self.assertEqual(request('GET',Host='attacker.example')[0],403)
            self.assertEqual(request('GET',Origin='https://evil.example')[0],403)
            self.assertEqual(request('POST','/api','{}')[0],403)
            self.assertEqual(request('GET','/../engine/editor.py')[0],404)
            headers={'Origin':server.origin,'Content-Type':'application/json','X-Studio-Mobile':'1'}
            r=request('POST','/api',json.dumps({'action':'library'}),**headers)
            self.assertTrue(json.loads(r[2])['ok'])
            with patch.object(server.companion, 'warm', return_value={'queued':True}):
                r=request('POST','/api',json.dumps({'action':'warm','project':self.pid,'revision':0,'frame':0}),**headers)
                self.assertEqual(json.loads(r[2]), {'ok':True,'result':{'queued':True}})
            with patch.object(server.companion,'segment',return_value=(b'0123456789','video/mp4')):
                r=request('GET',f'/media/{self.pid}/0/0.mp4',Range='bytes=2-5')
                self.assertEqual((r[0],r[2]),(206,b'2345'))
                self.assertEqual(request('GET',f'/media/{self.pid}/0/0.mp4',Range='bytes=30-')[0],416)
            server.user='owner@example.invalid'
            self.assertEqual(request('GET')[0],403)
            self.assertEqual(request('GET',**{'Tailscale-User-Login':'other@example.invalid'})[0],403)
            self.assertEqual(request('GET',**{'Tailscale-User-Login':'owner@example.invalid'})[0],200)
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_direct_plan_reuses_sources_after_cut_and_text_without_rendering(self):
        with patch.object(self.app.direct,'start'), patch.object(mobile.render,'render',side_effect=AssertionError('must not render montage')):
            first=self.app.query(self.req(action='directPlan'))
            self.assertNotIn(str(self.source),json.dumps(first))
            self.assertTrue(self.edit({'type':'splitAt','frame':120})['ok'])
            self.assertTrue(self.edit({'type':'text','kind':'graphics','id':'hook','text':'Cambia sin render'})['ok'])
            second=self.app.query(self.req(action='directPlan'))
            self.assertEqual({x['url'] for x in first['clips']},{x['url'] for x in second['clips']})
            self.assertEqual({x['url'] for x in first['audio']},{x['url'] for x in second['audio']})
            self.assertNotEqual(first['layers'][0]['url'],second['layers'][0]['url'])
            text=second['layers'][0]['url']
            self.assertIn(text,self.app.direct.status([text])['ready'])

    def test_audio_plan_is_bounded_by_source_chunks_and_preserves_fade_phase(self):
        p=copy.deepcopy(self.original)
        p['clips']=[dict(p['clips'][0],length=1800,fadeIn=150,fadeOut=150,**{'in':750})]
        p['assets'][0]['duration']=1800
        with patch.object(self.app.direct,'start'):
            plan=self.app.direct.plan(p)
        voice=[a for a in plan['audio'] if a['role']=='voice']
        self.assertEqual([round(a['length']) for a in voice],[5,30,25])
        self.assertEqual([a['source'] for a in voice],[25,0,0])
        self.assertEqual([a['fadeOffset'] for a in voice],[0,5,35])
        self.assertTrue(all(a['fadeLength']==60 for a in voice))
        self.assertEqual([a['deClickOffset'] for a in voice],[0,5,35])
        self.assertTrue(all(a['deClickLength']==60 for a in voice))
        self.assertEqual([a['start'] for a in voice],[0,5,35])

    def test_direct_proxy_build_is_playable_and_small(self):
        d=self.app.direct
        url=d.resource(self.original['assets'][0]);name=url.rsplit('/',1)[1]
        d.build(name,d.jobs[name])
        asset=mobile.render.probe(d.folder/name)
        self.assertLessEqual(max(asset['width'],asset['height']),640)
        self.assertFalse(asset['audio'])
        self.assertAlmostEqual(asset['duration'],10,places=1)
        url=d.resource(self.original['assets'][0],audio=True);name=url.rsplit('/',1)[1]
        d.build(name,d.jobs[name]);self.assertLessEqual(mobile.render.probe(d.folder/name)['duration'],30.1)

    def test_unreadable_source_does_not_block_the_queue(self):
        from subprocess import TimeoutExpired
        from direct import transcode
        d=self.app.direct
        video=d.resource(self.original['assets'][0]);audio=d.resource(self.original['assets'][0],audio=True)
        def build(name,spec):
            if spec['kind']=='video':raise TimeoutExpired('metadata',10)
            (d.folder/name).write_bytes(b'complete')
        d.running=True
        with patch.object(d,'build',side_effect=build):d.work()
        result=d.status([video,audio])
        self.assertEqual(result['failed'],[video]);self.assertEqual(result['ready'],[audio]);self.assertEqual(result['remaining'],0)
        with patch('direct.subprocess.run',return_value=SimpleNamespace(returncode=0)) as run:
            transcode(['-version'],30)
            self.assertEqual(run.call_args.kwargs['timeout'],150)

    def test_native_ranges_stream_without_whole_file_reads(self):
        server=mobile.serve(self.work/'projects',self.work/'range-runtime',port=0)
        name='a'*32+'.mp4';(server.companion.direct.folder/name).write_bytes(b'0123456789')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with patch.object(Path,'read_bytes',side_effect=AssertionError('whole file read')):
                c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                c.request('GET','/native/'+name,headers={'Range':'bytes=2-5'})
                r=c.getresponse();self.assertEqual(r.status,206);self.assertEqual(r.read(),b'2345');c.close()
                c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                c.request('HEAD','/native/'+name,headers={'Range':'bytes=-3'})
                r=c.getresponse();self.assertEqual(r.status,206);self.assertEqual(r.getheader('Content-Length'),'3');self.assertEqual(r.read(),b'');c.close()
        finally:server.shutdown();server.server_close();thread.join()

    def test_aborted_media_response_does_not_attempt_a_second_write(self):
        handler=object.__new__(mobile.Handler)
        handler.path=f'/media/{self.pid}/0/0.mp4'
        handler.headers={}
        handler.allowed=lambda:True
        handler.server=SimpleNamespace(companion=SimpleNamespace(segment=lambda *args:(b'video','video/mp4')))
        handler.send=Mock(side_effect=BrokenPipeError('client disconnected'))
        handler.error=Mock()
        handler.do_GET()
        handler.send.assert_called_once()
        handler.error.assert_not_called()


if __name__ == '__main__':
    unittest.main()
