# -*- coding: utf-8 -*-
import inspect
from spade.agent import Agent
from loguru import logger

class RPCAgent(Agent):
    """
    Agent with the capabilities to perform RPC (Remote procedure calls).
    It includes registering and calling methods on other agents.
    """
    def __init__(self, jid: str, password: str, *args, **kwargs):
        super().__init__(jid, password, *args, **kwargs)

    async def _hook_plugin_after_connection(self, *args, **kwargs):
        try:
            await super()._hook_plugin_after_connection(*args, **kwargs)
        except AttributeError:
            logger.debug("_hook_plugin_after_connection is undefined")

        self.rpc = self.RPCComponent(self.client)
    
    class RPCComponent:
        """
        Component for providing RPCAgents the XEP-009 Jabber RPC service.
        """

        def __init__(self, client):
            self.client = client
            # Register xep_0009 plugin on the slixmpp client
            if 'xep_0009' not in self.client.plugin:
                self.client.register_plugin('xep_0009')
            
            # Register event handler for incoming RPC calls
            self.client.add_event_handler('jabber_rpc_method_call', self._handle_rpc_call)
            
            self._methods = {}
            self.rpc_server = self.RPCServerShim(self)

        class RPCServerShim:
            def __init__(self, component):
                self.component = component

            def register_method(self, handler, method_name=None, is_allowed=None):
                return self.component._register_method_raw(handler, method_name, is_allowed)

            def unregister_method(self, method_name):
                return self.component.unregister_method(method_name)

        def parse_param(self, param):
            from slixmpp.plugins.xep_0009.binding import _py2xml
            return _py2xml(param)

        def parse_params(self, params):
            from slixmpp.plugins.xep_0009.binding import py2xml
            return py2xml(*params)

        def get_param(self, param_xml):
            from slixmpp.plugins.xep_0009.binding import _xml2py
            return _xml2py(param_xml)

        def get_params(self, params_xml):
            from slixmpp.plugins.xep_0009.binding import xml2py
            return xml2py(params_xml)

        async def _resolve_jid(self, target_jid):
            import asyncio
            from slixmpp import JID
            target = JID(target_jid)
            if target.resource:
                return target.full

            bare_jid = target.bare

            # 1. Try to get it from the local SPADE Container (fastest for local agents)
            try:
                from spade.container import Container
                container = Container()
                agent = container.get_agent(bare_jid)
                if agent and agent.client and agent.client.boundjid:
                    resolved = str(agent.client.boundjid)
                    return resolved
            except Exception:
                pass

            # 2. Try to get it from the XMPP Roster
            try:
                resources = self.client.roster[bare_jid].resources
                if resources:
                    resource = list(resources.keys())[0]
                    resolved = f"{bare_jid}/{resource}"
                    return resolved
            except Exception:
                pass

            # Fallback to the bare JID directly
            return bare_jid

        async def call_method(self, jid, method_name, params):
            """
            This method is used to make an rpc call to the corresponding jid with the given parameters
            jid: JID of the peer to query
            method_name: Name of the method to perform the call
            params: Param or list of params to perform the call
            """
            resolved_jid = await self._resolve_jid(jid)

            if not isinstance(params, (list, tuple)):
                params = [params]

            from slixmpp.plugins.xep_0009.binding import py2xml, xml2py
            iq = self.client.plugin['xep_0009'].make_iq_method_call(resolved_jid, method_name, py2xml(*params))
            
            try:
                response = await iq.send()
            except Exception as e:
                logger.error(f"Error calling remote method {method_name} on {jid}: {e}")
                raise e

            response.enable('rpc_query')
            fault = response['rpc_query']['method_response']['fault']
            if fault is not None:
                from slixmpp.plugins.xep_0009.binding import xml2fault
                f = xml2fault(fault)
                raise Exception(f"RPC Remote Fault ({f['code']}): {f['string']}")
                
            return xml2py(response['rpc_query']['method_response']['params'])

        def register_method(self, handler, method_name=None, is_allowed=None):
            """
            This method is used to register an rpc method
            handler: function to perform when called
            method_name: name of the method to be called
            is_allowed: function that is called to find out if the method can be executed by the JID that calls it
            """
            if method_name is None:
                method_name = handler.__name__
            self._methods[method_name] = {
                'handler': handler,
                'is_allowed': is_allowed,
                'raw': False
            }

        def _register_method_raw(self, handler, method_name=None, is_allowed=None):
            if method_name is None:
                method_name = handler.__name__
            self._methods[method_name] = {
                'handler': handler,
                'is_allowed': is_allowed,
                'raw': True
            }

        def unregister_method(self, method_name):
            """
            This method unregisters a previously registered method
            method_name: name of the method to be unregistered
            """
            if method_name in self._methods:
                del self._methods[method_name]

        async def _handle_rpc_call(self, iq):
            iq.enable('rpc_query')
            method_name = iq['rpc_query']['method_call']['method_name']
            
            if method_name not in self._methods:
                error = self.client.plugin['xep_0009']._item_not_found(iq)
                error.send()
                return
                
            method_info = self._methods[method_name]
            is_allowed = method_info['is_allowed']
            handler = method_info['handler']
            raw = method_info['raw']
            
            if is_allowed is not None:
                allowed = is_allowed(iq['from'], method_name)
                if not allowed:
                    error = self.client.plugin['xep_0009']._forbidden(iq)
                    error.send()
                    return

            try:
                if raw:
                    if inspect.iscoroutinefunction(handler):
                        response = await handler(iq)
                    else:
                        response = handler(iq)
                    
                    import slixmpp
                    from slixmpp.xmlstream import ElementBase
                    if isinstance(response, slixmpp.Iq):
                        response.send()
                    elif isinstance(response, ElementBase):
                        reply = iq.reply()
                        reply.append(response)
                        reply.send()
                    else:
                        if response is None:
                            response_vals = []
                        elif not isinstance(response, (list, tuple)):
                            response_vals = [response]
                        else:
                            response_vals = response
                        from slixmpp.plugins.xep_0009.binding import py2xml
                        reply = self.client.plugin['xep_0009'].make_iq_method_response(iq['id'], iq['from'], py2xml(*response_vals))
                        reply.send()
                else:
                    from slixmpp.plugins.xep_0009.binding import xml2py, py2xml
                    params = xml2py(iq['rpc_query']['method_call']['params'])
                    
                    if inspect.iscoroutinefunction(handler):
                        response = await handler(*params)
                    else:
                        response = handler(*params)
                    
                    if response is None:
                        response_vals = []
                    elif not isinstance(response, (list, tuple)):
                        response_vals = [response]
                    else:
                        response_vals = response
                    
                    reply = self.client.plugin['xep_0009'].make_iq_method_response(iq['id'], iq['from'], py2xml(*response_vals))
                    reply.send()
                    
            except Exception as e:
                logger.exception(f"Error handling RPC call {method_name}")
                fault = {
                    'code': 500,
                    'string': str(e)
                }
                from slixmpp.plugins.xep_0009.binding import fault2xml
                self.client.plugin['xep_0009']._send_fault(iq, fault2xml(fault))