# -*- coding: utf-8 -*-
import unittest
import asyncio
from unittest.mock import MagicMock

import slixmpp
from slixmpp import Iq

from spade_rpc import RPCAgent

class TestSpadeRPC(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Register the xep_0009 stanza plugins on Iq for testing
        from slixmpp.xmlstream import register_stanza_plugin
        from slixmpp.plugins.xep_0009.stanza import RPCQuery, MethodCall, MethodResponse
        register_stanza_plugin(Iq, RPCQuery)
        register_stanza_plugin(RPCQuery, MethodCall)
        register_stanza_plugin(RPCQuery, MethodResponse)

        # We need a mock client that behaves like a slixmpp ClientXMPP
        self.mock_client = MagicMock()
        
        # We need to mock register_plugin and plugin access
        self.plugins = {}
        def register_plugin_mock(name):
            if name == 'xep_0009':
                # Create a mock xep_0009 plugin
                plugin = MagicMock()
                self.plugins[name] = plugin
                return plugin
        self.mock_client.register_plugin.side_effect = register_plugin_mock
        self.mock_client.plugin = self.plugins
        
        # Keep track of event handlers
        self.event_handlers = {}
        def add_event_handler_mock(event, handler):
            self.event_handlers[event] = handler
        self.mock_client.add_event_handler.side_effect = add_event_handler_mock

    async def test_sync_rpc_call(self):
        """Test registering and calling a synchronous method."""
        sync_comp = RPCAgent.RPCComponent(self.mock_client)
        
        def sync_add(a, b):
            return a + b

        sync_comp.register_method(sync_add, "add")

        # Simulate stanza
        from slixmpp.plugins.xep_0009.binding import py2xml
        iq = Iq()
        iq['type'] = 'set'
        iq['from'] = 'sender@example.com'
        iq.enable('rpc_query')
        iq['rpc_query']['method_call']['method_name'] = 'add'
        iq['rpc_query']['method_call']['params'] = py2xml(5, 3)

        # Mock the response generation
        sent_responses = []
        def make_iq_method_response_mock(id, to, params):
            resp = Iq()
            resp['id'] = id
            resp['to'] = to
            resp.enable('rpc_query')
            resp['rpc_query']['method_response']['params'] = params
            resp.send = lambda: sent_responses.append(resp)
            return resp
        
        self.plugins['xep_0009'].make_iq_method_response.side_effect = make_iq_method_response_mock

        # Call the registered event handler
        await sync_comp._handle_rpc_call(iq)
        
        # Verify the response
        self.assertEqual(len(sent_responses), 1)
        resp = sent_responses[0]
        result = sync_comp.get_params(resp['rpc_query']['method_response']['params'])
        self.assertEqual(result, [8])

    async def test_raw_rpc_call(self):
        """Test registering and calling a raw method that takes a stanza."""
        sync_comp = RPCAgent.RPCComponent(self.mock_client)
        
        def raw_handler(stanza):
            params = sync_comp.get_params(stanza['rpc_query']['method_call']['params'])
            method_name = params[0]
            # Just return the method name and sender
            return [method_name, str(stanza['from'])]

        sync_comp.rpc_server.register_method(raw_handler, "raw_test")

        # Simulate stanza
        from slixmpp.plugins.xep_0009.binding import py2xml
        iq = Iq()
        iq['type'] = 'set'
        iq['from'] = 'sender@example.com'
        iq.enable('rpc_query')
        iq['rpc_query']['method_call']['method_name'] = 'raw_test'
        iq['rpc_query']['method_call']['params'] = py2xml("hello")

        # Mock response generation
        sent_responses = []
        def make_iq_method_response_mock(id, to, params):
            resp = Iq()
            resp['id'] = id
            resp['to'] = to
            resp.enable('rpc_query')
            resp['rpc_query']['method_response']['params'] = params
            resp.send = lambda: sent_responses.append(resp)
            return resp
        
        self.plugins['xep_0009'].make_iq_method_response.side_effect = make_iq_method_response_mock

        # Call the handler
        await sync_comp._handle_rpc_call(iq)

        # Verify response
        self.assertEqual(len(sent_responses), 1)
        resp = sent_responses[0]
        result = sync_comp.get_params(resp['rpc_query']['method_response']['params'])
        self.assertEqual(result, ["hello", "sender@example.com"])

if __name__ == '__main__':
    unittest.main()
