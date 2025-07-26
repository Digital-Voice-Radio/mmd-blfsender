
CONFIG = { 
          'username': 'mon',
          'password': '***PASSWORD***',
          'dashboard_rx': 'wss://mmd.dvdmr.org/rx',
          'service_exchange': 'world.nzsip.nz',
          'trunks': {
              'PJSIP/nzsip': ( 'ignored', 'CALLSIGN', 'Display Name', ),
          'extensions': [ (60000,69999), ],
          'mysql': {
              'enabled': True,
              'host': '127.0.0.1',
              'user': 'user',
              'password': 'password',
              'database': 'asterisk'
          }
}

