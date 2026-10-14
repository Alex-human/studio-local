"""Mobile companion end-to-end invariants, using an isolated library and synthetic media."""
import concurrent.futures
import copy
import http.client
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'mobile'))
import server as mobile
import direct


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
        idle = patch.object(mobile.DirectMedia,'start',lambda self:None)  # Builds run only where a test asks for them.
        idle.start(); self.addCleanup(idle.stop)
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
        self.assertTrue(self.edit({'type':'delete','kind':'clips','id':p['clips'][1]['id']})['ok'])
        p = mobile.project.load(self.path)
        self.assertEqual([c['length'] for c in p['clips']],[120])
        self.assertEqual(p['graphics'][0]['length'],120)
        self.assertEqual(p['audio'],self.original['audio'])
        self.assertTrue(self.app.query(self.req(action='undo'))['ok'])
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
            fuera={'Sec-Fetch-Site':'cross-site','Sec-Fetch-Dest':'document'}
            self.assertEqual(request('GET',**fuera)[0],200)
            self.assertEqual(request('GET',**{**fuera,'Sec-Fetch-Dest':'iframe'})[0],403)
            self.assertEqual(request('GET','/icon.png',**fuera)[0],403)
            self.assertEqual(request('POST','/api','{}')[0],403)
            self.assertEqual(request('GET','/../engine/editor.py')[0],404)
            headers={'Origin':server.origin,'Content-Type':'application/json','X-Studio-Mobile':'1'}
            r=request('POST','/api',json.dumps({'action':'library'}),**headers)
            self.assertTrue(json.loads(r[2])['ok'])
            with patch.object(server.companion, 'warm', return_value={'queued':True}):
                r=request('POST','/api',json.dumps({'action':'warm','project':self.pid,'revision':0,'frame':0}),**headers)
                self.assertEqual(json.loads(r[2]), {'ok':True,'result':{'queued':True}})
            plan={'action':'directPlan','project':self.pid,'revision':0}
            r=request('POST','/api',json.dumps(plan),**headers)
            self.assertEqual(r[0],409);self.assertIn('recarga',json.loads(r[2])['error'],'a page loaded before the player changed is told to reload')
            self.assertTrue(json.loads(request('POST','/api',json.dumps({**plan,'player':mobile.PLAYER}),**headers)[2])['ok'])
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
        with patch.object(mobile.render,'render',side_effect=AssertionError('must not render montage')):
            first=self.app.query(self.req(action='directPlan'))
            self.assertNotIn(str(self.source),json.dumps(first))
            media={x['url'] for x in first['clips']+first['audio']}
            self.assertEqual(set(first['pending']),media,'only what the Mac still has to build is pending')
            self.assertEqual(set(self.app.direct.queues[1]),{url.rsplit('/',1)[1] for url in media},'opening queues the montage')
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
        plan=self.app.direct.plan(p)
        voice=[a for a in plan['audio'] if a['role']=='voice']
        self.assertEqual([round(a['length']) for a in voice],[5,10,10,10,10,10,5])
        self.assertEqual([a['source'] for a in voice],[5,0,0,0,0,0,0])
        self.assertEqual([a['fadeOffset'] for a in voice],[0,5,15,25,35,45,55])
        self.assertTrue(all(a['fadeLength']==60 for a in voice))
        self.assertEqual([a['deClickOffset'] for a in voice],[0,5,15,25,35,45,55])
        self.assertTrue(all(a['deClickLength']==60 for a in voice))
        self.assertEqual([a['start'] for a in voice],[0,5,15,25,35,45,55])

    def test_video_plan_splits_clips_at_source_chunks_and_keeps_their_phase(self):
        p=copy.deepcopy(self.original)
        p['clips']=[dict(p['clips'][0],length=1800,zoomEnd=1.2,motionOffset=40,**{'in':750})]
        p['assets'][0]['duration']=1800
        clips=self.app.direct.plan(p)['clips']
        self.assertEqual([c['id'] for c in clips],[f'clip:{n}' for n in range(2,9)])
        self.assertEqual([c['length'] for c in clips],[150,300,300,300,300,300,150])
        self.assertEqual([c['start'] for c in clips],[0,150,450,750,1050,1350,1650])
        self.assertEqual([c['in'] for c in clips],[150,0,0,0,0,0,0])
        self.assertEqual([c['motionOffset']-c['start'] for c in clips],[40]*7,'zoom keeps the phase of the whole clip')
        self.assertTrue(all(c['motionLength']==1800 and c['base'] for c in clips))
        self.assertEqual(len({c['url'] for c in clips}),7)
        # Fractional rates: every piece stays inside its own proxy and the pieces add up to the clip.
        p['fps']=60000/1001;p['clips'][0].update(length=2000,**{'in':17})
        clips=self.app.direct.plan(p)['clips']
        self.assertEqual(sum(c['length'] for c in clips),2000)
        for c in clips:
            self.assertGreaterEqual(c['in'],0)
            self.assertLess((c['in']+c['length']-1)/p['fps'],direct.CHUNK)
        # The source ends just after a chunk boundary: its tail holds the last real proxy instead of an empty one.
        p['assets'][0]['duration']=30.2;p['clips'][0].update(length=300,**{'in':1500})
        clips=self.app.direct.plan(p)['clips']
        self.assertEqual([c['id'] for c in clips],['clip:2'])
        # An overlay keeps its entrance phase and never extends past the montage.
        p['graphics']=[dict(id='over',type='video',asset='asset',start=100,length=900,offset=7,props={},**{'in':0})]
        layers=self.app.direct.plan(p)['layers']
        self.assertEqual([(g['start'],g['length'],g['offset']) for g in layers],[(100,200,7)])

    def test_desktop_plan_keeps_timing_and_audio_but_separates_hd_visuals(self):
        p=copy.deepcopy(self.original)
        p.update(width=1920,height=1080)
        p['assets'][0].update(width=1920,height=1080)
        p['graphics'].append(dict(id='over',type='video',asset='asset',start=0,length=60,props={},**{'in':0}))
        mobile.project.save(self.path,p)
        sd=self.app.query(self.req(action='directPlan'))
        hd=self.app.query(self.req(action='directPlan',size=1920))
        sharp=self.app.query(self.req(action='directPlan',size=1280))
        self.assertEqual((sd['width'],sd['height']),(640,360))
        self.assertEqual((sharp['width'],sharp['height']),(1280,720))
        self.assertEqual(sd['audio'],sharp['audio']);self.assertFalse({x['url'] for x in sharp['clips']}&{x['url'] for x in sd['clips']+hd['clips']})
        self.assertEqual((hd['width'],hd['height']),(1920,1080))
        self.assertEqual(sd['audio'],hd['audio'],'HD reuses exactly the same sound')
        for a,b in zip(sd['clips']+sd['layers'],hd['clips']+hd['layers']):
            self.assertNotEqual(a['url'],b['url'])
            for key in ('start','length','in','motionOffset','motionLength'):
                self.assertEqual(a.get(key),b.get(key))
        self.assertEqual(sd,self.app.query(self.req(action='directPlan',size=640)))
        self.assertEqual(mobile.project.load(self.path),p,'preview quality never edits the project')
        for invalid in (4096,True,'1920',None):
            with self.assertRaises(ValueError):self.app.query(self.req(action='directPlan',size=invalid))

    def test_hd_proxy_encodes_real_1080p_without_upscaling_small_sources(self):
        source=self.work/'hd.mp4'
        mobile.render.run(['-v','error','-f','lavfi','-i','testsrc2=size=1920x1080:rate=30:duration=1',
                          '-c:v','h264_videotoolbox','-b:v','8M','-pix_fmt','yuv420p',source])
        d=self.app.direct
        for asset,expected in ((dict(self.original['assets'][0],path=str(source),width=1920,height=1080),(1920,1080)),
                               (self.original['assets'][0],(160,90))):
            url=d.resource(asset,size=1920);name=url.rsplit('/',1)[1]
            d.build(name,d.jobs[name]);result=mobile.render.probe(d.folder/name)
            self.assertEqual((result['width'],result['height']),expected)
            self.assertFalse(result['audio'])

    def test_direct_proxy_build_is_playable_and_small(self):
        d=self.app.direct
        url=d.resource(self.original['assets'][0]);name=url.rsplit('/',1)[1]
        d.build(name,d.jobs[name])
        asset=mobile.render.probe(d.folder/name)
        self.assertLessEqual(max(asset['width'],asset['height']),640)
        data=(d.folder/name).read_bytes()
        self.assertLess(data.index(b'moov'),data.index(b'mdat'),'the index arrives before the samples')
        self.assertNotIn(b'ctts',data,'samples are in the order they are shown: the player feeds them as they come')
        self.assertFalse(asset['audio'])
        self.assertAlmostEqual(asset['duration'],10,places=1)
        url=d.resource(self.original['assets'][0],audio=True);name=url.rsplit('/',1)[1]
        d.build(name,d.jobs[name]);self.assertLessEqual(mobile.render.probe(d.folder/name)['duration'],10.1)
        self.assertEqual((d.folder/name).read_bytes()[4:12],b'ftypisom','WebKit decodes plain MP4 sound, not the M4A brand')

    def test_chunk_proxy_shows_the_source_at_its_own_position(self):
        source=self.work/'long.mp4'
        mobile.render.run(['-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=30:duration=25','-c:v','libx264','-pix_fmt','yuv420p',source])
        asset=dict(self.original['assets'][0],path=str(source),duration=25,audio=False)
        d=self.app.direct
        name=d.resource(asset,start=10).rsplit('/',1)[1]
        d.build(name,d.jobs[name])
        built=mobile.render.probe(d.folder/name)
        self.assertAlmostEqual(built['duration'],10,places=1)
        def frame(path,at):
            raw=mobile.render.run(['-v','error','-ss',at,'-i',path,'-frames:v','1','-f','rawvideo','-pix_fmt','gray','-'])
            return mobile.render.np.frombuffer(raw,dtype=mobile.render.np.uint8).astype(int)
        for at in (0,2.5,9.9):
            shown=frame(d.folder/name,at)
            same=abs(shown-frame(source,10+at)).mean();other=abs(shown-frame(source,10+at+.5)).mean()
            self.assertLess(same*3,other,f'chunk time {at} must show source time {10+at}')
        tail=d.resource(asset,start=20).rsplit('/',1)[1]
        d.build(tail,d.jobs[tail])
        self.assertAlmostEqual(mobile.render.probe(d.folder/tail)['duration'],5,places=1)

    def test_playhead_goes_first_and_one_background_build_leaves_a_worker_free(self):
        d=self.app.direct;asset=dict(self.original['assets'][0],duration=100)
        a,b,c=(d.resource(asset,start=n).rsplit('/',1)[1] for n in (0,10,20))
        d.queue(2,[a,b,c],1);d.queue(1,[b,'/native/unregistered.mp4']);d.queue(0,[c])
        self.assertEqual(d.queues,[[c],[b],[a]],'a tier keeps registered media only, up to its limit')
        self.assertEqual(d.take(),(c,0))
        self.assertEqual(d.take(),(b,1))
        d.background=True
        self.assertEqual(d.take(),(None,0),'a second background build would leave no worker for the playhead')
        d.queue(0,['/native/'+a])
        self.assertEqual(d.take(),(a,0),'the playhead is served while a background build runs')
        d.background=False
        self.assertEqual(d.take(),(None,0),'media taken from one tier is not built again from another')

    def test_cache_drops_the_longest_unused_first_and_nothing_just_used(self):
        d=self.app.direct;now=time.time()
        for n,age in enumerate((4000,3000,60,30,10)):
            path=d.folder/f'{n:032x}.mp4'
            with path.open('wb') as file:file.truncate(2700*1024**2)  # Sparse: no disk is written.
            os.utime(path,(now-age,now-age))
        d.prune()
        self.assertEqual(sorted(p.name[31] for p in d.folder.glob('*.mp4')),['2','3','4'])

    def test_library_prepares_short_montages_whole_and_long_ones_by_their_first_minute(self):
        d=self.app.direct
        self.app.prepare(list(self.app.catalog().values()))
        self.assertEqual(sorted(n[-3:] for n in d.queues[2]),['m4a','mp4'])
        self.assertEqual(d.jobs[next(n for n in d.queues[2] if n.endswith('mp4'))]['size'],1280,'the library is ready in the picture a phone asks for first')
        with patch.object(d,'plan',side_effect=AssertionError('an unchanged montage is not planned again')):
            self.app.prepare(list(self.app.catalog().values()))
        with patch.object(mobile.time,'sleep',side_effect=[None,SystemExit]), patch.object(self.app,'prepare') as prepare:
            self.assertRaises(SystemExit,self.app.watch)
        self.assertEqual(prepare.call_count,1,'the Mac prepares a changed library on its own, once')
        p=mobile.project.load(self.path)
        p['assets'][0]['duration']=2000;p['clips'][0]['length']=30000;p['graphics']=[]
        mobile.project.save(self.path,p)
        self.app.prepare(list(self.app.catalog().values()))
        self.assertEqual(sorted(n[-3:] for n in d.queues[2]),['m4a']*7+['mp4']*7)
        d.queue(1,d.queues[2])
        with patch.object(self.app,'prepare'):
            self.app.query({'action':'library'})
        self.assertEqual(d.queues[1],[],'leaving a montage stops preparing the rest of it')
        self.source.with_name('gone.mp4').write_bytes(b'');p['assets'][0]['path']=str(self.source.with_name('gone.mp4'))
        mobile.project.save(self.path,p);self.source.with_name('gone.mp4').unlink()
        self.app.prepare(list(self.app.catalog().values()))
        self.assertEqual(d.queues[2],[],'a montage without its source does not break the library')

    def test_service_leaves_when_its_executable_or_code_is_replaced_but_never_during_a_write(self):
        def sleep(_):
            if slept.call_count==2:self.app.active.add('writing')
            if slept.call_count==3:self.app.active.clear()
        with patch.object(mobile,'running',side_effect=['a','a',None,'b','b']), patch.object(mobile.os,'_exit',side_effect=SystemExit) as leave, \
             patch.object(mobile.time,'sleep',side_effect=sleep) as slept, patch.object(self.app,'prepare'):
            self.assertRaises(SystemExit,self.app.watch)
        leave.assert_called_once_with(0)
        self.assertEqual(slept.call_count,3,'the same file, one being replaced and a write under way are no reason to leave')
        engine=self.work/'editor'/'engine';engine.mkdir(parents=True);(engine/'project.py').write_text('')
        with patch.object(mobile,'ROOT',engine.with_name('mobile')):
            loaded=mobile.running()
            self.assertEqual(mobile.running(),loaded)
            os.utime(engine/'project.py',ns=(1,1))
            self.assertNotEqual(mobile.running(),loaded,'an engine changed on the Mac is not the one this service loaded')

    def test_phone_reports_are_appended_and_bounded(self):
        self.app.query({'action':'clientLog','entries':[{'event':'played','ms':120},'x',{'event':'error','message':'m'*5000}]})
        lines=(self.work/'runtime'/'client.log').read_text().splitlines()
        self.assertEqual((len(lines),json.loads(lines[0])['ms']),(2,120));self.assertLessEqual(len(lines[1]),2000)

    def test_unreadable_source_does_not_block_the_queue(self):
        from subprocess import TimeoutExpired
        from direct import transcode
        d=self.app.direct
        video=d.resource(self.original['assets'][0]);audio=d.resource(self.original['assets'][0],audio=True)
        def build(name,spec):
            if spec['kind']=='video':raise TimeoutExpired('metadata',10)
            (d.folder/name).write_bytes(b'complete')
        d.queue(0,[video,audio]);d.workers=1
        with patch.object(d,'build',side_effect=build):d.work()
        self.assertEqual((d.workers,d.queues[0]),(0,[]))
        result=d.status([video,audio])
        self.assertEqual(result['failed'],[video]);self.assertEqual(result['ready'],[audio])
        self.assertEqual(d.queues[0],[],'a failed source is not rebuilt behind the report')
        self.assertEqual(d.status([video])['failed'],[],'a failure is reported once')
        self.assertEqual(d.queues[0],[video.rsplit('/',1)[1]],'asking again retries it')
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
