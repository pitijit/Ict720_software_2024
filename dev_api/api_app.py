import os
import sys
import logging
from datetime import datetime, timedelta
from pytz import timezone
import json

from fastapi import FastAPI, Request, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pymongo import MongoClient

# timezone config
tz = timezone(os.getenv('TZ', None))
if tz is None:
    logging.error('TZ undefined.')
    sys.exit(1)


# logging configuration
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# pymongo configuration
mongo_host = os.getenv('MONGO_HOST', None)
if mongo_host is None:
    logging.error('MONGO_HOST undefined.')
    sys.exit(1)
mongo_port = os.getenv('MONGO_PORT', None)
if mongo_port is None:
    logging.error('MONGO_PORT undefined.')
    sys.exit(1)
mongo_client = MongoClient(mongo_host, int(mongo_port))

# start instance
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get('/api/devreg/{dev_id}')
async def on_devreg(dev_id: str, request: Request):
    resp = {'status': 'OK'}
    # call database
    dev_db = mongo_client.dev_db
    # register new dev_id
    timestamp = datetime.now(tz=tz)
    dev_reg = dev_db.device
    new_dev = {
        'dev_id': dev_id,
        'car_driver_id': None,
        'created_at': None,
        'registered_at': timestamp
    }
    dev_id = dev_reg.insert_one(new_dev).inserted_id
    resp['dev_id'] = str(dev_id)
    # register new dev_log for the new dev_id
    dev_log = dev_db.device_log
    new_devlog = {
        'dev_id': dev_id,
        'status': 'offline',
        'latest_hb': 0,
        'CMD': False,
        'prev_iter_timestamp': 0, # for actual use; for backend, not users
        #'prev_iter_timestamp': 0, # for mock test only
        'slp_counter': 0, # sleep counter; for LINE Bot alert backend
        'alert_delay_counter': 0 # for LINE Bot alert backend
    }
    dev_id_log = dev_log.insert_one(new_devlog).inserted_id
    resp['log'] = str(dev_id_log)
    return jsonable_encoder(resp)

@app.get('/devregister')
async def on_devregister(request: Request):
    return templates.TemplateResponse(
        request=request, name="devregister.html", content={"dummy":0}
    )

@app.post('/api/devregister')
async def on_devregister(request: Request):
    resp = {'status': 'OK'}
    # call databases
    timestamp = datetime.now(tz=tz)
    dev_db = mongo_client.dev_db
    dev_reg = dev_db.device
    car_db = mongo_client.car_db
    car_owner_db = car_db.car_owner
    data = await request.json()
    dev_doc = dev_reg.find_one({'dev_id': data['dev_id']}, {'_id': False})
    if dev_doc is not None:
        resp['error_message'] = f'409: duplicated dev_id is not acceptable'
        print(f'409: duplicated dev_id is not acceptable')
        raise HTTPException(status_code=409, detail="Duplicated dev_id is not acceptable")
        #return jsonable_encoder(resp)

    # check for abnormal case 2: missing info
    for key in data.keys():
        value = data[key]
        if value == "":
            resp['error_message'] = f'400: missing required info; {data[key]} is required'
            print(f'400: missing required info; {data[key]} is required')
            raise HTTPException(status_code=400, detail=f'missing required info; {data[key]} is required')
            #return jsonable_encoder(resp)

    # check for abnormal case 3: invalid admin_id, auth
    admins = list(car_owner_db.find({}, {'admin_id': True}))
    admin_id_list = [admin['admin_id'] for admin in admins]

    # invalid admin_id, auth inputted are not allowed
    if data['admin_id'] in admin_id_list:
        auth = data['auth']
        valid_auth = car_owner_db.find_one({'admin_id': data['admin_id']}, {'_id': 0, 'auth': 1})['auth']
        
        if auth == str(valid_auth):
            print(f'admin: {data["admin_id"]} authorized new device register.')
            data['registered_at'] = timestamp
            # store only dev_reg data
            keys = ['dev_id', 'car_driver_id', 'created_at', 'registered_at']
            new_devreg = {k: v for k, v in data.items() if k in keys}
            # register new device to dev_reg database
            dev_objid = dev_reg.insert_one(new_devreg).inserted_id
            resp['dev_id'] = str(dev_objid)
            # register new dev_log for the new device
            dev_log = dev_db.device_log
            new_devlog = {
                'dev_id': data['dev_id'],
                'status': 'offline',
                'latest_hb': 0, # most recent heartbeat
                'CMD': False,
                'prev_iter_timestamp': 0, # for actual use || for backend, not users
                #'prev_iter_timestamp': 0, # for mock test only || for backend, not users
                'slp_counter': 0, # sleep counter; for LINE Bot alert backend
                'alert_delay_counter': 0 # for LINE Bot alert backend
            }
            dev_id_log = dev_log.insert_one(new_devlog).inserted_id
            resp['log'] = str(dev_id_log)
            return jsonable_encoder(resp)
        
        else:
            resp['error_message'] = "Invalid admin_id or auth"
            print("Invalid admin_id or auth")
            raise HTTPException(status_code=400, detail="Invalid admin_id or auth. Authorization Failed.")
    else:
        resp['error_message'] = "Invalid admin_id or auth"
        print("Invalid admin_id or auth")
        raise HTTPException(status_code=400, detail="Invalid admin_id or auth. Authorization Failed.")


@app.get('/devregedit')
async def on_devregedit(request: Request):
    return templates.TemplateResponse(
        request=request, name="devregister_edit.html", content={"dummy":0}
    )

@app.post('/api/devregedit')
async def on_devregedit(request: Request):
    resp = {'status': 'OK'}
    # call the database
    timestamp = datetime.now(tz=tz)
    dev_db = mongo_client.dev_db
    dev_reg = dev_db.device
    car_db = mongo_client.car_db
    car_owner_db = car_db.car_owner
    data = await request.json()
    dev_doc = dev_reg.find_one({'dev_id': data['dev_id']}, {'_id': False})
    # check #1: allow to edit only registered devices' data
    if dev_doc is None:
        resp['error_message'] = f"403: Failed to Edit Data; {data['dev_id']} is not registered."
        raise HTTPException(status_code=403, detail=f"403: Failed to Edit Data; {data['dev_id']} is not registered.")
    # check #2: all fields must be inputted
    for key in data.keys():
        value = data[key]
        if value == "":
            resp['error_message'] = f'400: missing required info; {data[key]} is required.'
            raise HTTPException(status_code=400, detail=f'400: missing required info; {data[key]} is required.')
        
    # check for abnormal case 3: invalid admin_id, auth
    admins = list(car_owner_db.find({}, {'admin_id': True}))
    admin_id_list = [admin['admin_id'] for admin in admins]

    # invalid admin_id, auth inputted are not allowed
    if data['admin_id'] in admin_id_list:
        auth = data['auth']
        valid_auth = car_owner_db.find_one({'admin_id': data['admin_id']}, {'_id': 0, 'auth': 1})['auth']
        
        if auth == str(valid_auth):
            print(f'admin: {data["admin_id"]} authorized new device register.')
            data['registered_at'] = timestamp
            # update data
            dev_reg.update_one({'dev_id': data['dev_id']}, {'$set':{'car_driver_id':data['car_driver_id']}})
            dev_reg.update_one({'dev_id': data['dev_id']}, {'$set':{'created_at':data['created_at']}})
            dev_reg.update_one({'dev_id': data['dev_id']}, {'$set':{'registered_at':timestamp}})
            
            resp['edited_dev'] = str(dev_reg.find_one({'dev_id': data['dev_id']}, {'_id': False}))
            return jsonable_encoder(resp)
        
        else:
            resp['error_message'] = "Invalid admin_id or auth"
            print("Invalid admin_id or auth")
            raise HTTPException(status_code=400, detail="Invalid admin_id or auth. Authorization Failed.")
    else:
        resp['error_message'] = "Invalid admin_id or auth"
        print("Invalid admin_id or auth")
        raise HTTPException(status_code=400, detail="Invalid admin_id or auth. Authorization Failed.")


@app.get('/api/alldevlist')
async def on_alldevlist(request: Request):
    resp = {'status':'OK'}
    dev_db = mongo_client.dev_db
    dev_reg = dev_db.device
    resp['devices'] = list(dev_reg.find({}, {'_id':False}))
    return jsonable_encoder(resp)

@app.get('/api/alldevevts')
async def on_alldevevts(request: Request):
    resp = {'status':'OK'}
    dev_db = mongo_client.dev_db
    dev_evts = dev_db.device_events
    resp['dev_evts'] = list(dev_evts.find({}, {'_id':False}))
    return jsonable_encoder(resp)

@app.get('/api/devlist/{dev_id}')
async def on_devlist(dev_id: str, request: Request):
    resp = {'status': 'OK'}
    dev_db = mongo_client.dev_db
    dev_reg= dev_db.device
    resp['devices'] = list(dev_reg.find({'dev_id': dev_id}, {'_id': False}))
    return jsonable_encoder(resp)

@app.get('/api/devevts/{dev_id}')
async def on_devevts(dev_id: str, request: Request):
    resp = {'status': 'OK'}
    dev_db = mongo_client.dev_db
    dev_evts = dev_db.device_events
    resp['dev_id'] = dev_id
    #resp['car_driver_id'] = None # No need here. It is already in the document collection
    resp['dev_evts'] = list(dev_evts.find({'dev_id': dev_id}, {'_id': False}))
    return jsonable_encoder(resp)

@app.get('/api/alldevlog')
async def on_devlog(request: Request):
    ''' See the current status of each registered device '''
    resp = {'status':'OK'}
    dev_db = mongo_client.dev_db
    dev_log = dev_db.device_log
    resp['log'] = list(dev_log.find({}, {'_id': False}))
    return jsonable_encoder(resp)

@app.get('/api/log/{dev_id}')
async def on_log(dev_id: str, request: Request):
    resp = {'status':'OK'}
    # query and return all logs for a device
    dev_db = mongo_client.dev_db
    dev_evts = dev_db.device_events
    resp['dev_id'] = dev_id
    resp['log'] = list(dev_evts.find_one({'dev_id': dev_id}, {'_id': False}))
    return jsonable_encoder(resp)

@app.get('/api/alldevstatus')
async def on_devlog(request: Request):
    ''' See the current status of each registered device '''
    resp = {'status':'OK'}
    dev_db = mongo_client.dev_db
    dev_log = dev_db.device_log
    resp['log'] = list(dev_log.find({}, {'_id': 0, 'dev_id': 1, 'status': 1}))
    return jsonable_encoder(resp)

@app.get('/api/devstatus/{dev_id}')
async def on_log(dev_id: str, request: Request):
    resp = {'status':'OK'}
    # query and return all logs for a device
    dev_db = mongo_client.dev_db
    dev_log = dev_db.device_log
    resp['dev_id'] = dev_id
    resp['log'] = list(dev_log.find({'dev_id': dev_id}, {'_id': 0, 'dev_id': 1, 'status': 1}))
    return jsonable_encoder(resp)

@app.get('/api/activate/{dev_id}')
async def on_devactivate(dev_id: str, request: Request):
    resp = {'status':'OK'}
    dev_db = mongo_client.dev_db
    dev_log = dev_db.device_log
    dev_log.update_one({'dev_id': dev_id}, {'$set':{'CMD': True}})
    resp['CMD_updated'] = list(dev_log.find({'dev_id': dev_id}, {'_id': 0, 'dev_id': 1, 'CMD': 1}))
    return jsonable_encoder(resp)

@app.get('/api/deactivate/{dev_id}')
async def on_devactivate(dev_id: str, request: Request):
    resp = {'status':'OK'}
    dev_db = mongo_client.dev_db
    dev_log = dev_db.device_log
    dev_log.update_one({'dev_id': dev_id}, {'$set':{'CMD': False}})
    resp['CMD_updated'] = list(dev_log.find({'dev_id': dev_id}, {'_id': 0, 'dev_id': 1, 'CMD': 1}))
    return jsonable_encoder(resp)

@app.get('/api/activateall')
async def on_devactivate(request: Request):
    resp = {'status':'OK'}
    dev_db = mongo_client.dev_db
    dev_log = dev_db.device_log
    dev_logs = list(dev_log.find({}, {'dev_id': True}))
    dev_id_list = [device['dev_id'] for device in dev_logs]

    for dev_id in dev_id_list:
        dev_log.update_one({'dev_id': dev_id}, {'$set':{'CMD': True}})
        
    resp['CMD_updated'] = list(dev_log.find({}, {'_id': 0, 'dev_id': 1, 'CMD': 1}))
    return jsonable_encoder(resp)

@app.get('/api/deactivateall')
async def on_devactivate(request: Request):
    resp = {'status':'OK'}
    dev_db = mongo_client.dev_db
    dev_log = dev_db.device_log
    dev_logs = list(dev_log.find({}, {'dev_id': True}))
    dev_id_list = [device['dev_id'] for device in dev_logs]

    for dev_id in dev_id_list:
        dev_log.update_one({'dev_id': dev_id}, {'$set':{'CMD': False}})
        
    resp['CMD_updated'] = list(dev_log.find({}, {'_id': 0, 'dev_id': 1, 'CMD': 1}))
    return jsonable_encoder(resp)

