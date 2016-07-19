"""
Define the community machanism.
Author:www.muzixing.com

Date                Work
2015/7/30           define abstract
2015/8/28           delete features_handler.
"""

from ryu.base import app_manager
from ryu.ofproto import ofproto_v1_3
from ryu.controller.handler import set_ev_cls
from ryu.controller.handler import set_ev_handler
from ryu.lib.ip import ipv4_to_bin
from ryu.lib.mac import haddr_to_bin

from ryu.openexchange.network import network_aware
from ryu.openexchange.network import network_monitor
from ryu.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import CONFIG_DISPATCHER

from ryu.topology import event, switches

from ryu.openexchange.event import oxp_event
from ryu.openexchange import oxproto_v1_0
from ryu.openexchange import oxproto_v1_0_parser
from ryu.openexchange.oxproto_v1_0 import OXPP_ACTIVE
from ryu.openexchange.oxproto_v1_0 import OXPPS_LIVE
from ryu.openexchange import topology_data
from ryu.openexchange.routing_algorithm.routing_algorithm import get_paths
from ryu import cfg

CONF = cfg.CONF


class Abstract(app_manager.RyuApp):
    """Abstract complete the network abstract
    and handle the network information update."""

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    _CONTEXTS = {
        "Network_Aware": network_aware.Network_Aware,
        "Network_Monitor": network_monitor.Network_Monitor,
    }

    def __init__(self, *args, **kwargs):
        super(Abstract, self).__init__(*args, **kwargs)
        self.name = 'oxp_abstract'
        self.args = args
        self.network = kwargs["Network_Aware"]
        self.monitor = kwargs["Network_Monitor"]
        # self.domain = None
        self.oxparser = oxproto_v1_0_parser
        self.oxproto = oxproto_v1_0
        self.topology = topology_data.Domain()

    @set_ev_cls(oxp_event.EventOXPVportStateChange, MAIN_DISPATCHER)
    def vport_handler(self, ev):
        vport_no = ev.vport_no
        state = ev.state
        domain = ev.domain

        reason = None
        if ev.state == OXPPS_LIVE:
            reason = self.oxproto.OXPPR_ADD
        else:
            reason = self.oxproto.OXPPR_DELETE

        vport = self.oxparser.OXPVPort(vport_no=vport_no, state=state)
        vport_state_change = self.oxparser.OXPVportStatus(
            domain, vport=vport, reason=reason)
        domain.send_msg(vport_state_change)

    @set_ev_cls(oxp_event.EventOXPHostStateChange, MAIN_DISPATCHER)
    def host_update_handler(self, ev):
        domain = ev.domain
        hosts = []
        for host in ev.hosts:
            h = self.oxparser.OXPHost(ip=ipv4_to_bin(host[0]),
                                      mac=haddr_to_bin(host[1]),
                                      mask=255, state=host[2])
            hosts.append(h)
        host_update = self.oxparser.OXPHostUpdate(domain, hosts)
        domain.send_msg(host_update)

    @set_ev_cls(oxp_event.EventOXPHostRequest, MAIN_DISPATCHER)
    def host_request_handler(self, ev):
        domain = ev.msg.domain
        host_info = self.network.access_table
        hosts = []
        for key in host_info:
            h = self.oxparser.OXPHost(ip=ipv4_to_bin(host_info[key][0]),
                                      mac=haddr_to_bin(host_info[key][1]),
                                      mask=255, state=OXPP_ACTIVE)
            hosts.append(h)
        host_reply = self.oxparser.OXPHostReply(domain, hosts)
        domain.send_msg(host_reply)

    def create_links(self, vport=[], capabilities={}):
        links = []
        for src in vport:
            for dst in vport:
                src_dpid, src_port_no = self.network.vport[src]
                dst_dpid, dst_port_no = self.network.vport[dst]

                if src_dpid != dst_dpid and src_dpid > dst_dpid:
                    if src_dpid in capabilities:
                        if dst_dpid in capabilities[src_dpid]:
                            cap = capabilities[src_dpid][dst_dpid]
                        else:
                            continue
                    else:
                        continue

                    link = self.oxparser.OXPInternallink(src_vport=int(src),
                                                         dst_vport=int(dst),
                                                         capability=str(cap))
                    links.append(link)
        return links

    def get_capabilities(self):
        self.topology.ports = self.network.vport.keys()
        if len(self.topology.ports):
            capabilities, paths = get_paths(self.network.graph, CONF.oxp_flags)
            self.topology.capabilities = capabilities
            self.topology.paths = paths
            return self.create_links(self.topology.ports, capabilities)
        return None

    def topo_reply(self, domain):
        links = self.get_capabilities()
        topo_reply = self.oxparser.OXPTopoReply(domain, links=links)
        domain.send_msg(topo_reply)

    @set_ev_cls(oxp_event.EventOXPTopoRequest, MAIN_DISPATCHER)
    def topo_request_handler(self, ev):
        domain = ev.msg.domain
        self.topology.domain_id = domain.id
        self.oxproto = domain.oxproto
        self.oxparser = domain.oxproto_parser

        self.topo_reply(domain)

    @set_ev_cls(oxp_event.EventOXPSBPPacketIn, MAIN_DISPATCHER)
    def sbp_packet_in_handler(self, ev):
        msg = ev.msg
        domain = ev.domain
        msg.serialize()

        sbp_pkt = self.oxparser.OXPSBP(domain, data=msg.buf)
        domain.send_msg(sbp_pkt)
        return
