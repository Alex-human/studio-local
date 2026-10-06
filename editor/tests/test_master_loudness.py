import re, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'engine'))
import project, render

def level(path):
    """Integrated loudness (LUFS) and true peak (dBFS) of a file's audio."""
    report=subprocess.run([str(render.FF),'-hide_banner','-nostdin','-i',str(path),'-vn','-af','ebur128=peak=true','-f','null','-'],capture_output=True,text=True).stderr
    summary=report[report.rfind('Summary'):]
    return float(re.search(r'I:\s+(-?[\d.]+)',summary).group(1)),float(re.search(r'Peak:\s+(-?[\d.]+|-inf)',summary).group(1))

class MasterLoudness(unittest.TestCase):
    """Masters leave Studio at −14 LUFS with effect peaks limited; previews keep the project level."""
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='studio-loudness-');root=cls.root=Path(cls.temp.name)
        quiet='0.12*sin(2*PI*220*t)+if(between(t\\,3\\,3.03)\\,0.95*sin(2*PI*1000*t)\\,0)'   # voz a unos −21 LUFS y un golpe de efecto casi a 0 dBFS
        render.run(['-v','error','-f','lavfi','-i','testsrc2=size=128x72:rate=30:duration=6','-f','lavfi','-i',f'aevalsrc={quiet}:s=48000:d=6',
                    '-c:v','libx264','-pix_fmt','yuv420p','-c:a','pcm_s16le','-shortest',root/'src.mov'])
        render.run(['-v','error','-f','lavfi','-i','testsrc2=size=128x72:rate=30:duration=6','-f','lavfi','-i','anullsrc=r=48000:cl=stereo',
                    '-c:v','libx264','-pix_fmt','yuv420p','-c:a','pcm_s16le','-shortest',root/'silent.mov'])
        def make(src):
            p=project.new(width=128,height=72,fps=30)
            p['assets']=[dict(id='s',kind='video',path=str(root/src),name='S',duration=6,width=128,height=72,fps=30,audio=True)]
            p['clips']=[dict(id='a',asset='s',length=180,**{'in':0})]
            return project.validate(p)
        cls.p,cls.silent=make('src.mov'),make('silent.mov')
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def export(self,p,name,preview=False):
        with patch.dict(render.ENCODER,{'master':['-c:v','libx264','-preset','ultrafast'],'preview':['-c:v','libx264','-preset','ultrafast']}):
            return render.render(p,self.root/name,preview=preview)['path']
    def test_master_reaches_minus_14_lufs_with_limited_peaks(self):
        loudness,peak=level(self.export(self.p,'master'))
        self.assertAlmostEqual(loudness,-14,delta=0.6)
        self.assertLess(peak,0)
    def test_preview_keeps_project_level(self):
        self.assertLess(level(self.export(self.p,'preview',preview=True))[0],-19)
    def test_silence_stays_silent(self):
        self.assertLessEqual(level(self.export(self.silent,'silent'))[0],-70)

if __name__=='__main__':unittest.main()
