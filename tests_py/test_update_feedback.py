from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'targets/linux-sbc-hub75/runtime'))
from scoreboard_device.runtime import DeviceRuntime
from scoreboard_device.status_server import DASHBOARD_PAGE

class UpdateFeedbackTests(unittest.TestCase):
    def check(self, remote, ancestor=False):
        calls=[]
        runtime=DeviceRuntime.__new__(DeviceRuntime)
        runtime._find_git_repo=lambda: Path(__file__).resolve().parents[1]
        def run(cmd,**kwargs):
            calls.append(cmd)
            if 'ls-remote' in cmd: output=remote+'\trefs/heads/main\n'
            elif 'rev-parse' in cmd: output='abcdef1\n'
            elif 'merge-base' in cmd:
                if not ancestor: raise subprocess.CalledProcessError(1,cmd)
                output=''
            elif 'log' in cmd: output=''
            else: raise AssertionError(cmd)
            return subprocess.CompletedProcess(cmd,0,output,'')
        with patch('scoreboard_device.runtime.subprocess.run',side_effect=run): result=runtime._web_check_update()
        self.assertFalse(any('fetch' in c for c in calls))
        return result

    def test_candidate_includes_main_so_not_an_update(self):
        result=self.check('1234567'+'0'*33,ancestor=True)
        self.assertFalse(result['available']); self.assertIn('Test release',result['message'])

    def test_same_commit_and_new_main_update(self):
        self.assertFalse(self.check('abcdef1'+'0'*33)['available'])
        self.assertTrue(self.check('1234567'+'0'*33)['available'])

    def test_real_dashboard_script_resets_button_after_auth_failure(self):
        start=DASHBOARD_PAGE.index('async function applyUpdate()')
        end=DASHBOARD_PAGE.index('// Reveal Controls',start)
        function=DASHBOARD_PAGE[start:end]
        harness='''const vm=require('node:vm');const assert=require('node:assert/strict');
const button={disabled:false,textContent:'Apply Update'};const toast={};let removed=false;
const pinInput={value:'123456'};const context={confirm:()=>true,
 document:{getElementById:id=>id==='btn-apply-update'?button:id==='update-toast'?toast:pinInput},
 localStorage:{removeItem:()=>{removed=true}},forgetBroadcastPin:()=>{removed=true},
 adminFetch:async()=>({ok:false,status:401,json:async()=>({error:'Household PIN is required'})})};
vm.createContext(context);vm.runInContext(FUNCTION,context);
context.applyUpdate().then(()=>{assert.equal(button.disabled,false);assert.equal(button.textContent,'Apply Update');
assert.match(toast.textContent,/household PIN was not accepted/);assert.match(toast.textContent,/No update started/);assert.equal(removed,true)});
'''.replace('FUNCTION',json.dumps(function))
        subprocess.run(['node','-e',harness],check=True,capture_output=True,text=True)
