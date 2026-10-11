from __future__ import annotations
import json,sys,tempfile,unittest,urllib.request,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'targets/linux-sbc-hub75/runtime'))
from tests_py import test_device_runtime as helpers
from scoreboard_device.runtime import DeviceRuntime
from shared_py.arcade import create_game,start_game
from shared_py.arcade_frame import arcade_frame,DIM,WHITE

class HouseholdPreferencesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=helpers.DeviceRuntimeTests()._staged_runtime_root(Path(self.tmp.name))
        p=self.root/'config/runtime-config.json'; c=json.loads(p.read_text());c['status']={'host':'127.0.0.1','port':0};p.write_text(json.dumps(c))
        self.r=DeviceRuntime(self.root,output_kind='simulator');self.r.status_server.start()
        self.url=f'http://127.0.0.1:{self.r.status_server.server.server_address[1]}'
    def tearDown(self):
        self.r.status_server.close();self.r.bluetooth_remote.close();self.r.buttons.close();self.r.output.close();self.tmp.cleanup()
    def config(self):return json.load(urllib.request.urlopen(self.url+'/api/config'))
    def post(self,payload,pin='123456',origin=None,path='/api/config'):
        headers={'Content-Type':'application/json','X-Scoreboard-Broadcast-Pin':pin}
        if origin:headers['Origin']=origin
        return json.load(urllib.request.urlopen(urllib.request.Request(self.url+path,method='POST',data=json.dumps(payload).encode(),headers=headers)))
    def test_household_pin_saves_quiet_hours_and_each_layout_and_survives_reload(self):
        for layout in ('classic','broadcastRows','broadcastLogos'):
            result=self.post({'expectedVersion':self.config()['version'],'layoutPreset':layout,'quietHours':{'enabled':True,'start':'22:00','end':'07:00','behavior':'sleep'}})
            self.assertTrue(result['ok']);self.assertEqual(layout,result['config']['layoutPreset']);self.assertEqual('sleep',result['config']['quietHours']['behavior'])
        saved=json.loads((self.root/'config/project.json').read_text())
        self.assertEqual('broadcastLogos',saved['designOverrides']['layoutPreset'])
        other=DeviceRuntime(self.root,output_kind='simulator')
        try:self.assertEqual('broadcastLogos',other._web_get_config()['layoutPreset'])
        finally:other.bluetooth_remote.close();other.buttons.close();other.output.close();other.status_server.server.server_close()
    def test_bad_pin_cross_origin_and_software_updates_are_rejected(self):
        original=self.config()
        for pin,origin,path in [('000000',None,'/api/config'),('123456','http://elsewhere.invalid','/api/config'),('000000',None,'/api/update/apply')]:
            with self.assertRaises(urllib.error.HTTPError) as e:self.post({'expectedVersion':original['version'],'layoutPreset':'broadcastRows'},pin,origin,path)
            self.assertIn(e.exception.code,(401,403))
        self.assertEqual(original,self.config())
    def test_invalid_layout_and_stale_save_do_not_overwrite_preferences(self):
        version=self.config()['version']
        with self.assertRaises(urllib.error.HTTPError) as e:self.post({'expectedVersion':version,'layoutPreset':'not-a-layout'})
        self.assertEqual(400,e.exception.code)
        self.post({'expectedVersion':version,'layoutPreset':'broadcastRows'})
        with self.assertRaises(urllib.error.HTTPError) as e:self.post({'expectedVersion':version,'layoutPreset':'classic'})
        self.assertEqual(409,e.exception.code);self.assertEqual('broadcastRows',self.config()['layoutPreset'])

class SnakeWallGeometryTests(unittest.TestCase):
    def test_every_edge_cell_touches_wall_without_overlap_or_gap(self):
        def pixel(frame,x,y):return tuple(frame.data[(y*128+x)*4:(y*128+x+1)*4])
        # Each head occupies exactly one two-pixel grid cell beside the wall.
        for cell,wall in [({'x':1,'y':8},(1,16)),({'x':62,'y':8},(126,16)),({'x':16,'y':3},(32,5)),({'x':16,'y':14},(32,30))]:
            s=start_game(create_game('snake'));s['body']=[cell];s['food']=None
            f=arcade_frame(s)
            self.assertEqual(DIM,pixel(f,*wall))
            for dx in (0,1):
                for dy in (0,1):self.assertEqual(WHITE,pixel(f,cell['x']*2+dx,cell['y']*2+dy))
