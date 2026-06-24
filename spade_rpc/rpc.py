# -*- coding: utf-8 -*-
import inspect
import aioxmpp
import aioxmpp.rpc.xso as rpc_xso
import datetime as dt

from spade.agent import Agent

from loguru import logger

# Patch aioxmpp.rpc.RPCServer to support async handlers transparently
original_handle = aioxmpp.rpc.RPCServer._handle_method_call

async def patched_handle_method_call(self, stanza):
    response = await original_handle(self, stanza)
    if inspect.isawaitable(response):
        response = await response
    return response

aioxmpp.rpc.RPCServer._handle_method_call = patched_handle_method_call

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

        type_class = {
            int: rpc_xso.i4,
            int: rpc_xso.integer,
            str: rpc_xso.string,
            float: rpc_xso.double,
            str: rpc_xso.base64,
            bool: rpc_xso.boolean,
            dt.datetime: rpc_xso.datetime,
            list: rpc_xso.array,
            dict: rpc_xso.struct
        }

        class_type = {v: k for k, v in type_class.items()}

        def __init__(self, client):
            self.client = client
            self.rpc_client = self.client.summon(aioxmpp.RPCClient)
            self.rpc_server = self.client.summon(aioxmpp.RPCServer)

        def parse_param(self, param):
            """
            This function parses a param or list of params into the appropiate rpc_xso class.
            param: a python parameter.
            returns rpc_xso.Value class with the corresponding rpc_xso value.
            """
            if type(param) == list:
                value = rpc_xso.array(rpc_xso.data([self.parse_param(x) for x in param]))
            elif type(param) == dict:
                members = [rpc_xso.member(rpc_xso.name(key), self.parse_param(value)) for key, value in param.items()]
                value = rpc_xso.struct(members)
            else:
                value = self.type_class[type(param)](param)
            
            return rpc_xso.Value(value)

        def parse_params(self, params):
            """
            This function parses the list of params into the corresponding rpc_xso.Param class.
            params: list of params to be parsed
            returns rpc_xso.Params with the list of rcp_xso parameters
            """
            return rpc_xso.Params([rpc_xso.Param(self.parse_param(x)) for x in params])

        def get_param(self, xso_param):
            """
            This function parses a rpc_xso param into a python usable param.
            xso_param: rpc_xso param to be parsed.
            returns corresponding python usable param
            """
            if type(xso_param) == rpc_xso.array:
                return [self.get_param(x.value) for x in xso_param.data.data]
            elif type(xso_param) == rpc_xso.struct:
                return {member.name.name: self.get_param(member.value.value) for member in xso_param.members}
            else:
                return self.class_type[type(xso_param)](xso_param.value)

        def get_params(self, xso_params):
            """
            This function parses the list of rpc_xso params into python usable params.
            xso_param: xso_params to be parsed
            returns list of corresponding python usable param
            """
            return [self.get_param(param.value.value) for param in xso_params.params]

        async def call_method(self, jid, method_name, params):
            """
            This method is used to make an rpc call to the corresponding jid with the given parameters
            jid: JID of the peer to query
            methodName: Name of the method to perform the call
            params: Param or list of params to perform the call
            """
            if not isinstance(params, list):
                params = [params]

            query = rpc_xso.Query(
                rpc_xso.MethodCall(
                    rpc_xso.MethodName(method_name),
                    self.parse_params(params)
                )
            )

            response = await self.rpc_client.call_method(aioxmpp.JID.fromstr(jid), query)
            return self.get_params(response.payload.params)

        def register_method(self, handler, method_name=None, is_allowed=None):
            """
            This method is used to register an rpc method
            handler: function to perform when called
            method_name: name of the method to be called
            is_allowed: function that is called to find out if the method can be executed by the JID that calls it
            """
            def method_wrapper(stanza):
                params = self.get_params(stanza.payload.payload.params)

                response = handler(*params)
                
                if not isinstance(response, list):
                    response = [response]
                
                query = rpc_xso.Query(
                    rpc_xso.MethodResponse(
                        self.parse_params(response)
                    )
                )

                return query

            return self.rpc_server.register_method(method_wrapper, method_name, is_allowed)

        def unregister_method(self, method_name):
            """
            This method unregisters a previously registered method
            method_name: name of the method to be unregistered
            """
            return self.rpc_server.unregister_method(self, method_name)


class AsyncRPCComponent(RPCAgent.RPCComponent):
    def register_method(self, handler, method_name=None, is_allowed=None):
        """
        This method is used to register an async rpc method
        handler: async function to perform when called
        method_name: name of the method to be called
        is_allowed: function that is called to find out if the method can be executed by the JID that calls it
        """
        async def method_wrapper(stanza):
            params = self.get_params(stanza.payload.payload.params)
            response = await handler(*params)
            
            if not isinstance(response, list):
                response = [response]
            
            query = rpc_xso.Query(
                rpc_xso.MethodResponse(
                    self.parse_params(response)
                )
            )
            return query

        return self.rpc_server.register_method(method_wrapper, method_name, is_allowed)

    def unregister_method(self, method_name):
        """
        This method unregisters a previously registered method
        method_name: name of the method to be unregistered
        """
        return self.rpc_server.unregister_method(method_name)


class AsyncRPCAgent(RPCAgent):
    """
    Agent with the capabilities to perform async RPC (Remote procedure calls).
    """
    async def _hook_plugin_after_connection(self, *args, **kwargs):
        try:
            await super(RPCAgent, self)._hook_plugin_after_connection(*args, **kwargs)
        except AttributeError:
            logger.debug("_hook_plugin_after_connection is undefined")

        self.rpc = AsyncRPCComponent(self.client)