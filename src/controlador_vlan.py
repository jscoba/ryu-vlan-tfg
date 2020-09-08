# Aplicación RYU que reenvía paquetes basandose en una asignación dinámica de VLANs

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller import dpset
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import vlan
from ryu.lib.packet import ether_types
from ryu.lib import stplib
from ryu.lib import dpid as dpid_lib
from ryu.topology.api import get_link

from vlan_assigner import VlanAssigner

class VlanSwitch(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {
        'stplib': stplib.Stp
    }

    def __init__(self, *args, **kwargs):
        super(VlanSwitch,self).__init__(*args,**kwargs)
        self.mac_to_port = {}
        self.v = VlanAssigner()
        self.trunk_ports = {}

        self.stp = kwargs['stplib']

    """
    Función ejecutada al conectar un nuevo switch al controlador.
    """
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id

        # Instalar la regla que manda al controlador los paquetes desconocidos
        #
        # We specify NO BUFFER to max_len of the output action due to
        # OVS bug. At this moment, if we specify a lesser number, e.g.,
        # 128, OVS will send Packet-In with invalid buffer_id and
        # truncated packet data. In that case, we cannot output packets
        # correctly.  The bug has been fixed in OVS v2.1.0.
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)


    """
    Función que añade un nuevo flujo al switch. De la documentación de Ryu.
    """
    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, match=match,
                                    instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst)
        print(datapath.send_msg(mod))

    """
    Función que elimina los flujos de un switch. De la documentación de Ryu.
    """
    def delete_flow(self, datapath):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        for dst in self.mac_to_port[datapath.id].keys():
            match = parser.OFPMatch(eth_dst=dst)
            mod = parser.OFPFlowMod(
                datapath, command=ofproto.OFPFC_DELETE,
                out_port=ofproto.OFPP_ANY, out_group=ofproto.OFPG_ANY,
                priority=1, match=match)
            datapath.send_msg(mod)

    """
    Función encargada de limpiar las tablas de flujos si cae un enlace. De la documentación
    """
    @set_ev_cls(stplib.EventTopologyChange, MAIN_DISPATCHER)
    def _topology_change_handler(self, ev):
        dp = ev.dp
        dpid_str = dpid_lib.dpid_to_str(dp.id)
        msg = 'Receive topology change event. Flush MAC table.'
        self.logger.debug("[dpid=%s] %s", dpid_str, msg)

        if dp.id in self.mac_to_port:
            self.delete_flow(dp)
            del self.mac_to_port[dp.id]

    """
    Función encargada de comprobar que dos hosts pertenecen a la misma vlan
    """
    def vlan_compatibles(self,src,dst):
        vlan_src = self.v.match_vlan(src)
        vlan_dst = self.v.match_vlan(dst)
        for v in vlan_src:
            if v in vlan_dst: return v
        return False

    
    """
    Función que determina si un enlace es trunk o no usando descubrimiento de topología.
    """
    def is_trunk(self, dpid, port_no):
        links_list = get_link(self, dpid)
        links=[link.src.port_no for link in links_list]
        return (port_no in links)
    """
    Función que determina si un host es trunk o no.
    """
    def is_trunk_host(self, dpid, port_no, mac_dst):
        if (mac_dst in self.mac_to_port[dpid]) and (len(self.v.match_vlan(mac_dst)) > 1):
            print("{} es host trunk en el dpid {} puerto {}".format(mac_dst, dpid, port_no))
            return self.mac_to_port[dpid][mac_dst]==port_no
        else:
            return False

    @set_ev_cls(stplib.EventPortStateChange, MAIN_DISPATCHER)
    def _port_state_change_handler(self, ev):
        dpid_str = dpid_lib.dpid_to_str(ev.dp.id)
        of_state = {stplib.PORT_STATE_DISABLE: 'DISABLE',
                    stplib.PORT_STATE_BLOCK: 'BLOCK',
                    stplib.PORT_STATE_LISTEN: 'LISTEN',
                    stplib.PORT_STATE_LEARN: 'LEARN',
                    stplib.PORT_STATE_FORWARD: 'FORWARD'}
        self.logger.debug("[dpid=%s][port=%d] state=%s",
                          dpid_str, ev.port_no, of_state[ev.port_state])

    """
    Función encargada de manejar los paquetes entrantes e instalar las reglas necesarias.
    """
    @set_ev_cls(stplib.EventPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # get Datapath ID to identify OpenFlow switches.
        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})
        self.trunk_ports.setdefault(dpid,[])

        # analyse the received packets using the packet library.
        pkt = packet.Packet(msg.data)
        eth_pkt = pkt.get_protocol(ethernet.ethernet)
        dst = eth_pkt.dst
        src = eth_pkt.src

        # get the received port number from packet_in message.
        in_port = msg.match['in_port']

        # Librarnos de procesar los LLDP.
        if eth_pkt.ethertype==35020:
            return

        self.logger.info("packet in %s %s %s %s", dpid, src, dst, in_port)


        # learn a mac address to avoid FLOOD next time.
        self.mac_to_port[dpid][src] = in_port
        

        #Comprobar si es un paquete de tipo arp. Si lo es y el destino es ff:ff:ff:ff:ff:ff se manda en flood y ya
        if dst == "ff:ff:ff:ff:ff:ff":
            if dst == "ff:ff:ff:ff:ff:ff": #Si es broadcast se hace broadcast
                out_port = ofproto.OFPP_FLOOD
                src_vlan = self.v.match_vlan(src)[0]|0x1000
                actions =  [parser.OFPActionOutput(out_port)]
                if eth_pkt.ethertype == ether_types.ETH_TYPE_8021Q: #Si ya viene empaquetado lo mandamos con tag y sin tag  
                    actions =  actions + [parser.OFPActionPopVlan(), parser.OFPActionOutput(out_port)]

                else: #Si no viene empaquetado lo mandamos empaquetado y sin empaquetar.                    
                    actions = [parser.OFPActionPushVlan(), parser.OFPActionSetField(vlan_vid=src_vlan), parser.OFPActionOutput(out_port)]

                out = parser.OFPPacketOut(datapath=datapath,
                                      buffer_id=ofproto.OFP_NO_BUFFER,
                                      in_port=in_port, actions=actions,
                                      data=msg.data)
                datapath.send_msg(out)
                return True #Fin del paquete ARP broadcast.
                    

        # if the destination mac address is already learned,
        # decide which port to output the packet, otherwise FLOOD.
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD
        
        # Si el paquete trae un tag de vlan reenviamos normal.

        vlan_header = pkt.get_protocol(vlan.vlan) # Si no hay vlan es None
        num_vlan_headers = len(pkt.get_protocols(vlan.vlan))
        print(vlan_header)


        if num_vlan_headers: #eth_pkt.ethertype == ether_types.ETH_TYPE_8021Q:
            src_vlan=vlan_header.vid
            # Si es un puerto trunk reenviamos, si no quitamos el tag vlan
            if self.is_trunk(dpid, out_port) or self.is_trunk_host(dpid, out_port, dst):
                actions = [parser.OFPActionOutput(out_port)]
                self.logger.info("Paquete trunk de %s a %s por el dpid %s con vlan %s", src, dst, dpid, src_vlan)
            else:
                actions = [parser.OFPActionPopVlan(), parser.OFPActionOutput(out_port)]
                self.logger.info("Paquete acceso de %s a %s por el dpid %s con vlan %s va al puerto %s", src, dst, dpid, src_vlan, out_port)

                # Y si conocemos el puerto de salida instalamos un flow
            if out_port != ofproto.OFPP_FLOOD:
                match = parser.OFPMatch(in_port=in_port, eth_dst=dst, vlan_vid=(0x1000 | src_vlan))
                
                self.add_flow(datapath, 1, match, actions)
                #print(actions)
                print("Añadiendo flow a {}".format(dpid))

            # construct packet_out message and send it.
            out = parser.OFPPacketOut(datapath=datapath,
                                      buffer_id=ofproto.OFP_NO_BUFFER,
                                      in_port=in_port, actions=actions,
                                      data=msg.data)
            datapath.send_msg(out)

        # Si el paquete no trae tag vlan comprobamos que se puede enviar y mandamos.

        else:
            src_vlan = self.vlan_compatibles(src,dst)
            if src_vlan:
                src_vlan = src_vlan | 0x1000 # https://ryu-devel.narkive.com/uuM8veFB/ofpbac-bad-set-argument-received-when-set-field-of-vlan-id
                
                # Si va a un host trunk no poner etiqueta, si no pues se marca el paquete.
                #if self.is_trunk_host(dpid, out_port, dst):
                #    actions = [parser.OFPActionOutput(out_port)]
                #else:
                actions = [parser.OFPActionPushVlan(), parser.OFPActionSetField(vlan_vid=src_vlan), parser.OFPActionOutput(out_port)]
                
                if out_port != ofproto.OFPP_FLOOD:
                    match = parser.OFPMatch(in_port=in_port, eth_dst=dst, vlan_vid=0x0000)
                    self.add_flow(datapath, 1, match, actions)
                    #print(actions)
                    print("Añadiendo flow con taggeo vlan {} a {}".format(src_vlan, dpid))

                # construct packet_out message and send it.
                    out = parser.OFPPacketOut(datapath=datapath,
                                              buffer_id=ofproto.OFP_NO_BUFFER,
                                              in_port=in_port, actions=actions,
                                              data=msg.data)
                    datapath.send_msg(out)
                

            else: #Esto nunca debería darse porque no se han debido encontrar las macs entre ellos.
                match = parser.OFPMatch(eth_src=src, eth_dst=dst) #Estas dos macs no pueden hablarse entre si
                self.add_flow(datapath, 1, match, [])
                self.logger.info("paquete NO arp bloqueado entre %s y %s en %s", src, dst, dpid)
        
        