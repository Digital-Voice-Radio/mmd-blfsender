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
logger = logging.getLogger(__name__)

def is_ext_published(ext):
    if ext.isnumeric():
        num = int(ext)

        for chk in CONFIG['extensions']:
            if num >= chk[0] and num <= chk[1]:
                return True
    return False

async def websocket_sender(queue, ws):
    logger.info("mmblf:cue:conn: Starting Websocket Sender")
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
                    logger.debug(f"mmblf:wsc:send: {ev}")
                send = await ws.send_str(json.dumps(ev))
                queue.task_done()

        logger.critical("mmblf:wsc:connect: Disconnected")


async def websocket_reader(ws):
    logger.info("mmblf:wsr:conn: Starting Websocket Reader")
    async for msg in ws:
        if msg.type == aiohttp.WSMsgType.TEXT:
            data = json.loads(msg.data)
            if data.get('_data') == 'PONG':
                pass
            elif data.get('_data') == 'PING':
                await ws.send_str(json.dumps({'_data': 'PONG'}))
            else:
                logger.warning(f"mmblf:wsr:recv: Unknown packet {msg.data}")
        elif msg.type == aiohttp.WSMsgType.ERROR:
            break

    logger.critical("mmblf:wsr:conn: Websocket Reader has closed.")

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
        elif is_ext_published(ext):
            include = True

        if include:
            return data

async def process_event(e, ami, queue):
    #print(f'mmblf:ami:event: {e}')
    evt = e.get('Event')
    data = None

    if evt == 'FullyBooted':
        logger.info('mmblf:ami:conn: Successfully Connected')

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

            logger.info(f"mmblf:ami:conn: Connecting to AMI 127.0.0.1 5038 {CONFIG['username']}")
            await ami.connect_ami()
            logger.critical('mmblf:ami:conn: Disconnected From AMI')
        except Exception as e:
            logger.error(f'mmblf:ami:error {e}')




async def send_ping(queue):
    logger.info('mmblf:png:task: Starting pinger')
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
    logger.info('mmblf:fpx:conn: Starting Database Sender')
    while True:
        if cnx and cnx.is_connected():
            with cnx.cursor() as cursor:
                result = cursor.execute("SELECT username,default_extension, primary_group, displayname FROM userman_users")
                rows = cursor.fetchall()
                for (username,default_extension, primary_group, displayname) in rows:
                    #print(username,default_extension, primary_group, displayname) 
                    if ' ' in displayname:
                        (call, name) = displayname.split(' ', 1)
                    else:
                        name = displayname
                        call = ""
                    if is_ext_published(username):
                        await queue.put({'_data': 'phonebook',
                                   'extension': username,
                                   'displayname': name,
                                   'callsign': call,
                        })

        await asyncio.sleep(600)



async def launch():
    queue = asyncio.Queue()
    await(queue.put({"_data": "SYSTEM", "_service": CONFIG.get('service_exchange') }))
    session = aiohttp.ClientSession()

    loop = asyncio.get_event_loop()
    ami = AMIClient(host='127.0.0.1', port=5038, username=CONFIG.get('username'), secret=CONFIG.get('password'))

    ws = await session.ws_connect(CONFIG['dashboard_rx'])

    if CONFIG['mysql']['enabled']:
        logger.info('mmblf:fpx:conn: Connecting to MySQL')
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

