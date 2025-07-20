# MMD BLF/Phonebook Sender for PBX

## MultiMode Dashboard Sender for AMI DeviceState

Send realtime DeviceState and UserMan entries from FreePBX/Asterisk to the Multimode Dashboard Server.

The multimode dashboard server code will be available shortly.

## Installing

Clone the repository and run the install script:

```
git clone git@github.com:Digital-Voice-Radio/mmd-blfsender.git
cd mmd-blfsender
bash install.sh
```

Add a manager to your `/etc/asterisk/manager_custom.conf` (FreePBX) or `/etc/asterisk/manager.conf`.

Example:
```
[mmblfsender]
secret = ASTRONGPASSWORD
deny=0.0.0.0/0.0.0.0
permit=127.0.0.1/255.255.255.0
read = system,call,log,verbose,command,agent,user,config,command,dtmf,reporting,cdr,dialplan,originate,message
write = system,call,log,verbose,command,agent,user,config,command,dtmf,reporting,cdr,dialplan,originate,message
writetimeout = 5000
```

Edit your `/opt/mmblfsender/config.py` file, this file is copied from the _SAMPLE file if it does not already exist.

```
CONFIG = { 
          'username': 'mmblfsender',
          'password': 'ASTRONGPASSWORD',
          'dashboard_rx': 'wss://mmd.dvdmr.org/rx',
          'service_exchange': 'myexchange',
          'trunks': [ 'PJSIP/nzsip', ],
          'extensions': [ (60000,69999), ],
          'mysql': {
              'enabled': True,
              'host': '127.0.0.1',
              'user': 'user',
              'password': 'password',
              'database': 'asterisk'
          }
}
```
If you want to send a full address book and display names from your FreePBX Usermon enable mysql and set the database login credentials to match your `asterisk` database.  
