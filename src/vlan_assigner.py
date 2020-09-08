# Clase que asigna una VLAN dada una MAC

import re

class VlanAssigner():

    def __init__(self):
        self.vlans = [10,20,30] #Vlans disponibles

        self.default_vlan = 10 # Vlan por defecto

        self.macs_wildcards = {
            10 : [ #Vlan por defecto, tráfico general
                'c2:c3:ae:8e:bf:25' #Mac del servidor
            ],
            20 : [ #Vlan de seguridad
                '01:ab:*',
                'c2:c3:ae:8e:bf:25' #Mac del servidor
            ],
            30 : [ #Vlan de telefonía
                '02:cd:*',
                'c2:c3:ae:8e:bf:25', #Mac del servidor
                '48:*'
            ]
        }

    def match_vlan(self,mac):
        encontrado = False
        resultado = []

        for k,v in self.macs_wildcards.items():
            for exp in v:
                r = re.compile(exp)
                if r.match(mac):
                    encontrado = True
                    resultado.append(k)
        if not encontrado:
            resultado.append(self.default_vlan)
        
        resultado.sort()
        return resultado



def test_simple():
    v = VlanAssigner()
    assert v.match_vlan('01:ab:03:24:87:ef') == [20]

def test_simple2():
    v = VlanAssigner()
    assert v.match_vlan('02:cd:03:44:87:ef') == [30]

def test_re_from_begin():
    v = VlanAssigner()
    assert v.match_vlan('02:ab:02:cd:87:ef') == [10]

def test_default():
    v = VlanAssigner()
    assert v.match_vlan('02:db:03:24:87:ef') == [10]

def test_multiple():
    v = VlanAssigner()
    assert v.match_vlan('01:02:03:04:05:06') == [10,20,30]
            