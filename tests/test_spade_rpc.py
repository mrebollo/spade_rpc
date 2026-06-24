# -*- coding: utf-8 -*-
import unittest
import asyncio
import inspect
from unittest.mock import MagicMock

import aioxmpp
import aioxmpp.rpc
import aioxmpp.rpc.xso as rpc_xso

from spade_rpc import RPCAgent, AsyncRPCAgent, AsyncRPCComponent

class TestSpadeRPC(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_client = MagicMock()
        self.mock_disco = MagicMock()
        self.dependencies = {
            aioxmpp.disco.DiscoServer: self.mock_disco
        }
        
        def summon_mock(cls):
            if cls in self.dependencies:
                return self.dependencies[cls]
            inst = cls(self.mock_client, dependencies=self.dependencies)
            self.dependencies[cls] = inst
            return inst

        self.mock_client.summon.side_effect = summon_mock

    def test_monkeypatch_applied(self):
        """Verify that RPCServer's method handler is patched."""
        self.assertIsNotNone(aioxmpp.rpc.RPCServer._handle_method_call)

    async def test_sync_rpc_call(self):
        """Test registering and calling a synchronous method."""
        sync_comp = RPCAgent.RPCComponent(self.mock_client)
        
        def sync_add(a, b):
            return a + b

        sync_comp.register_method(sync_add, "add")

        # Simulate stanza
        param_a = rpc_xso.Param(rpc_xso.Value(rpc_xso.integer(5)))
        param_b = rpc_xso.Param(rpc_xso.Value(rpc_xso.integer(3)))
        xso_params = rpc_xso.Params([param_a, param_b])
        
        stanza_add = aioxmpp.IQ(
            type_=aioxmpp.IQType.SET,
            payload=rpc_xso.Query(
                rpc_xso.MethodCall(
                    rpc_xso.MethodName("add"),
                    xso_params
                )
            )
        )
        stanza_add.from_ = aioxmpp.JID.fromstr("sender@example.com")
        
        response = await sync_comp.rpc_server._handle_method_call(stanza_add)
        result = sync_comp.get_params(response.payload.params)
        self.assertEqual(result, [8])

    async def test_async_rpc_call(self):
        """Test registering and calling an asynchronous method."""
        async_comp = AsyncRPCComponent(self.mock_client)
        
        async def async_multiply(a, b):
            await asyncio.sleep(0.001)
            return a * b

        async_comp.register_method(async_multiply, "multiply")

        # Simulate stanza
        param_a = rpc_xso.Param(rpc_xso.Value(rpc_xso.integer(5)))
        param_b = rpc_xso.Param(rpc_xso.Value(rpc_xso.integer(3)))
        xso_params = rpc_xso.Params([param_a, param_b])
        
        stanza_multiply = aioxmpp.IQ(
            type_=aioxmpp.IQType.SET,
            payload=rpc_xso.Query(
                rpc_xso.MethodCall(
                    rpc_xso.MethodName("multiply"),
                    xso_params
                )
            )
        )
        stanza_multiply.from_ = aioxmpp.JID.fromstr("sender@example.com")
        
        response = await async_comp.rpc_server._handle_method_call(stanza_multiply)
        result = async_comp.get_params(response.payload.params)
        self.assertEqual(result, [15])

if __name__ == '__main__':
    unittest.main()
