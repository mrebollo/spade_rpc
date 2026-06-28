import asyncio
import spade
from spade_rpc import RPCAgent
from spade.behaviour import OneShotBehaviour

class HelloWorldAgent(RPCAgent):
    async def setup(self):
        # El servidor registra su método en el setup
        self.rpc.register_method(self.saludar, "saludar")
        print(f"[{self.jid}] Servidor listo. Método 'saludar' registrado.")

    async def saludar(self, name):
        print(f"[{self.jid}] Invocado método 'saludar' con parámetro: {name}")
        return f"¡Hola, {name}!"

class ClientAgent(RPCAgent):
    def __init__(self, jid, password, server_jid):
        super().__init__(jid, password)
        self.server_jid = server_jid

    async def setup(self):
        print(f"[{self.jid}] Cliente listo. Añadiendo comportamiento...")
        self.add_behaviour(self.CallSayHello())

    class CallSayHello(OneShotBehaviour):
        async def run(self):
            print(f"[{self.agent.jid}] Realizando llamada RPC a {self.agent.server_jid}...")
            try:
                # El cliente hace la llamada usando el componente RPC
                resultado = await self.agent.rpc.call_method(
                    self.agent.server_jid,
                    "saludar",
                    "Mundo"
                )
                print(f"[{self.agent.jid}] Respuesta recibida: {resultado}")
            except Exception as e:
                print(f"[{self.agent.jid}] Error en la llamada RPC: {e}")
            finally:
                # Detenemos el cliente una vez completada la llamada
                await self.agent.stop()

async def main():
    # 1. Iniciamos el servidor primero
    server = HelloWorldAgent("server@localhost", "password")
    print("Iniciando servidor...")
    await server.start()
    await asyncio.sleep(1.5)  # Damos tiempo a que se conecte y el servidor XMPP le asigne su JID real

    # Obtenemos el JID real completo con el que se ha conectado el servidor
    real_server_jid = str(server.client.boundjid)
    print(f"Servidor conectado con JID real: {real_server_jid}")

    # 2. Iniciamos el cliente pasándole el JID real del servidor
    client = ClientAgent("client@localhost", "password", real_server_jid)
    print("Iniciando cliente...")
    await client.start()

    while client.is_alive():
        await asyncio.sleep(0.5) 

    # Detenemos el servidor
    print("Deteniendo servidor...")
    await server.stop()
    print("Fin del ejemplo.")

if __name__ == "__main__":
    spade.run(main())
