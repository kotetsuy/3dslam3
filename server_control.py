#!/usr/bin/env python3
"""Start/stop only this project's detached server, with readiness and PID checks."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parent
RUN = ROOT/'run'
STATE = RUN/'server.json'
LOG = RUN/'server.log'


def process_stamp(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
        if fields[0] == 'Z':
            return None
        return fields[19]  # /proc stat field 22, process start ticks
    except (OSError,IndexError):
        return None


def owned(state):
    pid = state.get('pid')
    if not isinstance(pid,int) or pid <= 1 or process_stamp(pid) != state.get('start_ticks'):
        return False
    try:
        args = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        return (str(ROOT/'viewer_server.py').encode() in args
                and state['token'].encode() in args and os.getpgid(pid) == pid)
    except (OSError,KeyError):
        return False


def health(state, timeout=1):
    host = state['host']
    if host in ('0.0.0.0','::'):
        host = '127.0.0.1'
    url = f'http://{host}:{state["port"]}/api/health'
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url,timeout=timeout) as response:
        result = json.load(response)
    if result.get('instance_token') != state['token'] or result.get('pid') != state['pid']:
        raise RuntimeError('別のサーバーが同じポートで応答しています')
    return result


def terminate(state):
    if not owned(state):
        return
    # start_new_session gives this instance its own process group, including CPU jobs.
    group = state['pid']
    os.killpg(group,signal.SIGTERM)
    for _ in range(100):
        if process_stamp(group) is None:
            break
        time.sleep(.1)
    if owned(state):
        os.killpg(group,signal.SIGKILL)
        for _ in range(50):
            if process_stamp(group) is None:
                break
            time.sleep(.1)
    if owned(state):
        raise RuntimeError('サーバーを停止できませんでした')


def load_state():
    if not STATE.exists():
        return None
    try:
        return json.loads(STATE.read_text())
    except (OSError,ValueError) as exc:
        raise RuntimeError(f'管理ファイルを読めません: {STATE}') from exc


def start(args):
    state = load_state()
    if state and owned(state):
        if (state['host'],state['port'],state['cpu']) != (args.host,args.port,args.cpu):
            raise RuntimeError(f"既に {state['url']} で起動しています。設定変更は ./stop_all.sh 後に行ってください。")
        result = health(state)
        if not result.get('ready'):
            raise RuntimeError('サーバーがまだ準備中です')
        print(f'既に起動しています: {state["url"]} (PID {state["pid"]})')
        return
    python = ROOT/('DA3/.venv/bin/python' if args.cpu else 'DA3/.venv-rocm/bin/python')
    if not python.is_file():
        raise RuntimeError('実行環境がありません。setup_da3.sh / setup_da3_rocm.shを先に実行してください。')
    if not (ROOT/'DA3/checkpoints/model.safetensors').is_file() and not args.cpu:
        raise RuntimeError('DA3重みがありません。download_da3.pyを実行してください。')
    token = uuid.uuid4().hex
    command = [str(python),'-u',str(ROOT/'viewer_server.py'),'--host',args.host,'--port',str(args.port),
               '--instance-token',token]
    if not args.cpu:
        command.append('--warmup-rocm')
    print('サーバーを起動しています。'+('CPUモード。' if args.cpu else 'ROCm・DA3モデルを初期化してウォームアップします。'),flush=True)
    with LOG.open('ab',buffering=0) as log:
        log.write(f'\n--- start {time.strftime("%Y-%m-%d %H:%M:%S")} ---\n'.encode())
        child = subprocess.Popen(command,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                                 start_new_session=True,close_fds=True)
    state = dict(pid=child.pid,start_ticks=process_stamp(child.pid),token=token,host=args.host,port=args.port,
                 cpu=args.cpu,url=f'http://{args.host}:{args.port}/')
    STATE.write_text(json.dumps(state,indent=2)+'\n')
    (RUN/'server.pid').write_text(str(child.pid)+'\n')
    begin = time.monotonic()
    try:
        last_notice = begin
        while time.monotonic()-begin < args.timeout:
            if child.poll() is not None:
                raise RuntimeError(f'サーバーが終了しました (exit {child.returncode})。ポート競合やROCm環境をログで確認してください。')
            try:
                result = health(state)
                if result.get('ready') and (args.cpu or result.get('rocm',{}).get('ready')):
                    print(f'起動しました: {state["url"]} (PID {child.pid})',flush=True)
                    if not args.cpu:
                        print('ROCm準備完了: '+result['rocm']['device']+' / DA3 float32・4枚でウォームアップ済み',flush=True)
                    print(f'ログ: {LOG}\n停止: ./stop_all.sh',flush=True)
                    return
            except (OSError,ValueError,RuntimeError):
                pass
            if time.monotonic()-last_notice >= 10:
                print(f'初期化中… {time.monotonic()-begin:.0f}秒（ログ: {LOG}）',flush=True)
                last_notice = time.monotonic()
            time.sleep(.2)
        raise RuntimeError(f'{args.timeout}秒以内に準備が完了しませんでした')
    except BaseException:
        terminate(state)
        STATE.unlink(missing_ok=True)
        (RUN/'server.pid').unlink(missing_ok=True)
        raise


def stop():
    state = load_state()
    if not state:
        print('管理対象のサーバーは起動していません。')
        return
    if owned(state):
        print(f'サーバーを停止しています (PID {state["pid"]})…',flush=True)
        terminate(state)
        print('停止しました。ROCmモデルも解放されました。')
    else:
        print('管理対象のプロセスは既に終了しています。他のプロセスは停止しません。')
    STATE.unlink(missing_ok=True)
    (RUN/'server.pid').unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['start','stop'])
    parser.add_argument('--host',default=os.environ.get('HOST','0.0.0.0'))
    parser.add_argument('--port',type=int,default=int(os.environ.get('PORT','8080')))
    parser.add_argument('--cpu',action='store_true',help='Start without resident ROCm initialization')
    parser.add_argument('--timeout',type=float,default=180)
    args=parser.parse_args()
    if not 1<=args.port<=65535 or args.timeout<=0:
        parser.error('Invalid port or timeout')
    RUN.mkdir(parents=True,exist_ok=True)
    try:
        with (RUN/'control.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            start(args) if args.action=='start' else stop()
    except (RuntimeError,OSError,KeyboardInterrupt) as exc:
        print(f'エラー: {exc}\nログ: {LOG}',file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
