#!/usr/bin/python

from mn_wifi.net import Mininet_wifi
from mininet.node import RemoteController, OVSKernelSwitch, Host
from mn_wifi.node import Station, OVSKernelAP
from mn_wifi.cli import CLI
from mn_wifi.link import wmediumd
from mn_wifi.wmediumdConnector import interference
from mininet.link import TCLink, Intf
from mininet.log import setLogLevel, info
from subprocess import call


def myNetwork():

    net = Mininet_wifi(controller=RemoteController,link=wmediumd,
                       wmediumd_mode=interference)
                       
    info( '*** Adding controller\n' )

    c0 = net.addController('c0', port=6633)

    info( '*** Add switches/APs\n')
    s1 = net.addSwitch('s1', cls=OVSKernelSwitch, protocols="OpenFlow13")
    s2 = net.addSwitch('s2', cls=OVSKernelSwitch, protocols="OpenFlow13")
    s3 = net.addSwitch('s3', cls=OVSKernelSwitch, protocols="OpenFlow13")
    s4 = net.addSwitch('s4', cls=OVSKernelSwitch, protocols="OpenFlow13")
    ap1 = net.addAccessPoint('ap1', cls=OVSKernelAP, ssid='ap1-ssid',
                             channel='1', mode='g', position='583.0,178.0,0', protocols="OpenFlow13")

    info( '*** Add hosts/stations\n')
#    h1 = net.addHost('h1', cls=Host, ip='10.0.0.2/24', mac='00:00:00:00:00:01')
#    h2 = net.addHost('h2', cls=Host, ip='10.0.0.3/24', mac='00:00:00:00:00:02')
#    h3 = net.addHost('h3', cls=Host, ip='10.0.2.2/24', mac='48:23:00:00:00:02')
#    h4 = net.addHost('h4', cls=Host, ip='10.0.2.3/24', mac='48:23:00:00:00:03')
    
    h1 = net.addHost('h1', cls=Host, ip=None, mac='00:00:00:00:00:01')
    h2 = net.addHost('h2', cls=Host, ip=None, mac='00:00:00:00:00:02')
    h3 = net.addHost('h3', cls=Host, ip=None, mac='48:23:00:00:00:02')
    h4 = net.addHost('h4', cls=Host, ip=None, mac='48:23:00:00:00:03')
    
    
    router = net.addHost('router', cls=Host, mac='c2:c3:ae:8e:bf:25')
    
    sta1 = net.addStation('sta1', ip=None,
                           position='378.0,207.0,0')

    info("*** Configuring Propagation Model\n")
    net.setPropagationModel(model="logDistance", exp=3)

    info("*** Configuring wifi nodes\n")
    net.configureWifiNodes()

    info( '*** Add links\n')
    net.addLink(s1, s2)
    net.addLink(s2, s4)
    net.addLink(s4, s3)
    net.addLink(s3, s1)
    net.addLink(s2, s3)
    net.addLink(s1, s4)
    net.addLink(s2, h2)
    net.addLink(h1, s1)
    net.addLink(h3, s3)
    net.addLink(h4, s4)
    net.addLink(router,s1)
    net.addLink(s2, ap1)
    net.addLink(sta1, ap1)

    net.plotGraph(max_x=1000, max_y=1000)

    info( '*** Starting network\n')
    net.build()
    info( '*** Starting controllers\n')
    for controller in net.controllers:
        controller.start()

    info( '*** Starting switches/APs\n')
    net.get('s1').start([c0])
    net.get('s2').start([c0])
    net.get('s3').start([c0])
    net.get('s4').start([c0])
    net.get('ap1').start([c0])

    info( '*** Post configure nodes\n')
    for h in net.hosts:
        print ("disable ipv6")
        h.cmd("sysctl -w net.ipv6.conf.all.disable_ipv6=1")
        h.cmd("sysctl -w net.ipv6.conf.default.disable_ipv6=1")
        h.cmd("sysctl -w net.ipv6.conf.lo.disable_ipv6=1")
        
    for h in net.stations:
        print ("disable ipv6")
        h.cmd("sysctl -w net.ipv6.conf.all.disable_ipv6=1")
        h.cmd("sysctl -w net.ipv6.conf.default.disable_ipv6=1")
        h.cmd("sysctl -w net.ipv6.conf.lo.disable_ipv6=1")

    for sw in net.switches:
        print ("disable ipv6")
        sw.cmd("sysctl -w net.ipv6.conf.all.disable_ipv6=1")
        sw.cmd("sysctl -w net.ipv6.conf.default.disable_ipv6=1")
        sw.cmd("sysctl -w net.ipv6.conf.lo.disable_ipv6=1")
        
    info( '*** Configurar router\n')
    router.cmd("vconfig add router-eth0 10")
    router.cmd("vconfig add router-eth0 20")
    router.cmd("vconfig add router-eth0 30")
    router.cmd("ifconfig router-eth0.10 10.0.0.1 netmask 255.255.255.0")
    router.cmd("ifconfig router-eth0.20 10.0.1.1 netmask 255.255.255.0")
    router.cmd("ifconfig router-eth0.30 10.0.2.1 netmask 255.255.255.0")
    router.cmd("ifconfig router-eth0 0.0.0.0")
    
    
    info( '*** Iniciando el servidor DHCP \n')
    router.cmd("systemctl stop isc-dhcp-server")
    router.cmd("rm /var/lib/dhcp/dhcpd.leases")
    router.cmd("rm /var/lib/dhcp/dhcpd.leases~")
    router.cmd("touch /var/lib/dhcp/dhcpd.leases")
    router.cmd("dhcpd -4 -f --no-pid &")
    
    info( '*** Habilitando DHCP en los hosts\n')
    for h in net.hosts:
    	if h != router:
        	h.cmd("dhclient &")
        	
    for h in net.stations:
      	h.cmd("dhclient &")

    router.cmd("wireshark &")
    CLI(net)
    router.cmd("killall dhcpd")
    net.stop()


if __name__ == '__main__':
    setLogLevel( 'info' )
    myNetwork()

