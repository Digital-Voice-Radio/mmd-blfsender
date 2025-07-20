import asyncio
import aiohttp
import json

from pyami_asterisk import AMIClient

CONFIG = { 
          'username': 'mon',
          'password': 'Z33t8EaH7Nzv',
          'dashboard_rx': 'wss://mmd.dvdmr.org/rx',
          'service_exchange': 'world.nzsip.nz',
          'trunks': [ 'PJSIP/nzsip', ],
          'extensions': [ (60000,69999), ]
}

#Got {"Event": "DeviceStateChange", "Privilege": "call,all", "Device": "PJSIP/61282", "State": "INUSE"}
#Got {"Event": "ExtensionStatus", "Privilege": "call,all", "Exten": "61282", "Context": "ext-local", "Hint": "PJSIP/61282&Custom:DND61282,CustomPresence:61282", "Status": "0", "StatusText": "Idle"}

async def websocket_sender(queue, ws):
    print("mmblf:cue:conn: Starting Websocket Sender")
    await(queue.put({"_data": "SYSTEM",
                     "_service": CONFIG.get('service_exchange')
                    }))
    while True:
        while True:
            ev = None

            try:
                ev = queue.get_nowait()
            except Exception as e:
                await asyncio.sleep(1)
                pass

            if ev is not None:
                print(f"mmblf:wsc:send: {ev}")
                send = await ws.send_str(json.dumps(ev))
                queue.task_done()

        print("mmblf:wsc:connect: Disconnected")


async def websocket_reader(ws):
    print("mmblf:wsr:conn: Starting Websocket Reader")
    async for msg in ws:
        if msg.type == aiohttp.WSMsgType.TEXT:
            data = json.loads(msg.data)
            if data.get('_data') == 'PONG':
                pass
            elif data.get('_data') == 'PING':
                await ws.send_str(json.dumps({'_data': 'PONG'}))
            else:
                print(f"mmblf:wsr:recv: Unknown packet {msg.data}")
        elif msg.type == aiohttp.WSMsgType.ERROR:
            break

    print("mmblf:wsr:conn: Websocket Reader has closed.")

    loop = asyncio.get_event_loop()
    loop.stop()


async def do_DeviceStateChange(queue, e):

    device = e.get('Device')
    if device[:5] in ['IAX', 'PJSIP']:
        chn, ext = device.split('/')
        state = e.get('State')
        include = False

        data = {
            '_data': 'state',
            'Service': ext,
            'Device': device,
            'State': state,
            'DeviceType': 'extension'
        }

        if state == 'INVALID':
            include = False
        elif device in CONFIG['trunks']:
            data['DeviceType'] = 'trunk'
            include = True
        else:
            for chk in CONFIG['extensions']:
                num = int(ext)
                if num >= chk[0] and num <= chk[1]:
                    include = True

        if include:
            return data

async def process_event(e, ami, queue):
    #print(f'mmblf:ami:event: {e}')
    evt = e.get('Event')
    data = None

    if evt == 'FullyBooted':
        print('mmblf:ami:conn: Successfully Connected')

    elif evt in ['DeviceStateChange']:
        data = await do_DeviceStateChange(queue, e)

    if data is not None:
        #print(f'mmblf:queue:put: {data}')
        await queue.put(data)


async def ami_listener(ami, queue):

    async def all_events(e):
        await process_event(e, ami, queue)

    while True:
        ami.register_event(["FullyBooted", "ExtensionStatus", "DeviceStateChange"], callbacks=all_events)
        await asyncio.sleep(1)

        try:

            print(f"mmblf:ami:conn: Connecting to AMI 127.0.0.1 5038 {CONFIG['username']}")
            await ami.connect_ami()
            print('mmblf:ami:conn: Disconnected From AMI')
        except Exception as e:
            print('mmblf:ami:error {e}')




async def send_ping(queue):
    print('mmblf:wsc:ping: Starting pinger')
    while True:
        await queue.put({'_data': 'PING'})
        await asyncio.sleep(10)


async def ami_populate(ami, queue):

    async def result_handler(e):
        await process_event(e, ami, queue)

    ami.create_action({"Action": "CoreSettings"}, result_handler)
    while True:
        ami.create_action({"Action": "DeviceStateList"}, result_handler)
        await asyncio.sleep(60)


async def launch():
    queue = asyncio.Queue()
    session = aiohttp.ClientSession()

    loop = asyncio.get_event_loop()
    ami = AMIClient(host='127.0.0.1', port=5038, username=CONFIG.get('username'), secret=CONFIG.get('password'))

    ws = await session.ws_connect(CONFIG['dashboard_rx'])

    loop.create_task(websocket_sender(queue, ws), name="sender_task")
    loop.create_task(websocket_reader(ws), name="reader_task")

    loop.create_task(ami_listener(ami, queue), name="ami_listener")
    loop.create_task(ami_populate(ami, queue), name="ami_populate")

    loop.create_task(send_ping(queue), name="sender_ping")


if __name__ == '__main__':
    print('mmblf: Multimode Dashboard BLF Sender')
    print('(C) Copyright 2025, Jared Quinn VK2WAY <jared@jaredquinn.info>')
    print('')
    loop = asyncio.get_event_loop()
    loop.run_until_complete(launch())
    loop.run_forever()

