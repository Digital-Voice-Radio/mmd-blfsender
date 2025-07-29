import asyncio
import aiohttp
import json

from pyami_asterisk import AMIClient
import mysql.connector
import logging

from config import CONFIG

#Got {"Event": "DeviceStateChange", "Privilege": "call,all", "Device": "PJSIP/61282", "State": "INUSE"}
#Got {"Event": "ExtensionStatus", "Privilege": "call,all", "Exten": "61282", "Context": "ext-local", "Hint": "PJSIP/61282&Custom:DND61282,CustomPresence:61282", "Status": "0", "StatusText": "Idle"}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger('mmblf')

def is_ext_published(ext):
    if ext.isnumeric():
        num = int(ext)

        for chk in CONFIG['extensions']:
            if num >= chk[0] and num <= chk[1]:
                return True
    return False

async def websocket_sender(queue, ws):
    logger.info("cue:conn: Starting Websocket Sender")
    while True:
        while True:
            ev = None

            try:
                ev = queue.get_nowait()
            except Exception as e:
                await asyncio.sleep(1)
                pass

            if ev is not None:
                if ev.get('_data') not in [ 'PING', 'PONG', ]:
                    logger.debug(f"wsc:send: {ev}")
                send = await ws.send_str(json.dumps(ev))
                queue.task_done()

        logger.critical("wsc:connect: Disconnected")


async def websocket_reader(ws):
    logger.info("wsr:conn: Starting Websocket Reader")
    async for msg in ws:
        if msg.type == aiohttp.WSMsgType.TEXT:
            data = json.loads(msg.data)
            if data.get('_data') == 'PONG':
                pass
            elif data.get('_data') == 'PING':
                await ws.send_str(json.dumps({'_data': 'PONG'}))
            else:
                logger.warning(f"wsr:recv: Unknown packet {msg.data}")
        elif msg.type == aiohttp.WSMsgType.ERROR:
            break

    logger.critical("wsr:conn: Websocket Reader has closed.")

    loop = asyncio.get_event_loop()
    loop.stop()


async def do_DeviceStateChange(queue, e):

    device = e.get('Device')
    logger.info(f"{device}, {device[:4]}")
    if device[:4] in ['IAX2', 'PJSI', 'conf']:
        logger.info(e)
        if device[:4] == 'conf':
            chn, ext = device.split(':')
        else:
            chn, ext = device.split('/')

        state = e.get('State')
        include = False

        data = {
            '_data': 'state',
            'Service': ext,
            'Device': device,
            'State': state,
            'DeviceType': 'extension',
            'exchange': CONFIG.get('service_exchange'),
        }

        if state == 'INVALID':
            include = False

        elif device in CONFIG['trunks'].keys():
            data['DeviceType'] = 'trunk'
            include = True

        elif device in CONFIG['services']:
            data['DeviceType'] = 'service'
            include = True

        elif is_ext_published(ext):
            include = True

        if include:
            logger.info(data)
            return data

async def process_event(e, ami, queue):
    #print(f'mmblf:ami:event: {e}')
    evt = e.get('Event')
    data = None

    if evt == 'FullyBooted':
        logger.info('ami:conn: Successfully Connected')

    elif evt in ['DeviceStateChange']:
        logger.info(e)
        data = await do_DeviceStateChange(queue, e)

    elif evt in ['ExtensionStatus']:
        logger.info(e)

    if data is not None:
        logger.info(f'queue:put: {data}')
        await queue.put(data)


async def ami_listener(ami, queue):

    async def all_events(e):
        await process_event(e, ami, queue)

    while True:
        ami.register_event(["FullyBooted", "ExtensionStatus", "DeviceStateChange"], callbacks=all_events)
        await asyncio.sleep(1)

        try:

            logger.info(f"ami:conn: Connecting to AMI 127.0.0.1 5038 {CONFIG['username']}")
            await ami.connect_ami()
            logger.critical('ami:conn: Disconnected From AMI')
        except Exception as e:
            logger.error(f'ami:error {e}')




async def send_ping(queue):
    logger.info('png:task: Starting pinger')
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

async def database_sender(cnx, queue):
    logger.info('fpx:conn: Starting Database Sender')
    while True:
        for k,v in CONFIG.get('trunks').items():
            d = {'_data': 'phonebook',
                       'exchange': CONFIG.get('service_exchange'),
                       'extension': v[0],
                       'device': k,
                       'displayname': v[2],
                       'callsign': v[1],
                       'devicetype': 'trunk',
                       'state': 'UNMONITORED',
            }
            logger.info(d)
            await queue.put(d)

        if cnx and cnx.is_connected():
            with cnx.cursor() as cursor:
                result = cursor.execute("SELECT username,default_extension, title,primary_group, displayname FROM userman_users")
                rows = cursor.fetchall()
                for (username,default_extension, title, primary_group, displayname) in rows:
                    logger.info(f'{username},{default_extension},{displayname},{title},{primary_group})')
                    if ' ' in displayname:
                        (call, name) = displayname.split(' ', 1)
                    else:
                        name = displayname
                        call = ""

                    if is_ext_published(username):
                        st = 'UNKNOWN'
                        dt = 'extension'
                        if username in CONFIG['services'] or title == 'service':
                            dt = 'service'
                            st = 'UNMONITORED'
                        await queue.put({'_data': 'phonebook',
                                   'exchange': CONFIG.get('service_exchange'),
                                   'extension': username,
                                   'displayname': name,
                                   'callsign': call,
                                   'devicetype': dt,
                                   'state': st
                        })
        else:
            logger.info('fpx:conn: Not connected to mysql?')
        await asyncio.sleep(600)



async def launch():
    queue = asyncio.Queue()
    await(queue.put({"_data": "SYSTEM", "_service": CONFIG.get('service_exchange') }))
    session = aiohttp.ClientSession()

    loop = asyncio.get_event_loop()
    ami = AMIClient(host='127.0.0.1', port=5038, username=CONFIG.get('username'), secret=CONFIG.get('password'))

    ws = await session.ws_connect(CONFIG['dashboard_rx'])

    if CONFIG['mysql']['enabled']:
        logger.info('fpx:conn: Connecting to MySQL')
        cnx = mysql.connector.connect(user=CONFIG['mysql']['user'], password=CONFIG['mysql']['password'],
                              host=CONFIG['mysql']['host'],
                              database=CONFIG['mysql']['database'])

        loop.create_task(database_sender(cnx, queue), name="phonebook_sender")

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

