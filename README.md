# MicroServer

MicroServer é um servidor HTTP/WebSocket minimalista e assíncrono para MicroPython (testado em ESP32). Ele oferece roteamento baseado em decoradores, suporte a middleware, rotas dinâmicas, serviço de arquivos estáticos, helpers JSON e WebSockets.

Focado em baixo consumo de memória e facilidade de uso, é ideal para APIs RESTful e interfaces web simples em dispositivos IoT.

## Índice
- [Instalação](#instalação)
- [Quick Start](#quick-start)
- [Funcionalidades e Uso](#funcionalidades-e-uso)
  - [Roteamento Básico](#roteamento-básico)
  - [Rotas Dinâmicas](#rotas-dinâmicas)
  - [Arquivos Estáticos](#arquivos-estáticos)
  - [WebSockets](#websockets)
  - [Middleware](#middleware)
  - [Request e Response](#request-e-response)
  - [Streaming e Arquivos Grandes](#streaming-e-arquivos-grandes)
- [Arquitetura Interna](#arquitetura-interna)
- [Fluxo de Processamento](#fluxo-de-processamento)
- [Melhores Práticas](#melhores-práticas)
- [Exemplos](#exemplos)

## Instalação

### Via `mip` (Recomendado)
Para dispositivos com acesso à internet:
```python
import mip
mip.install("github:nicolasmmb/MicroServer")
```
Isso instala os arquivos necessários no diretório `/lib`.

### Instalação Manual
Copie os seguintes arquivos para a pasta `/lib` do seu dispositivo:
- `microserver.py`: Núcleo do servidor.
- `routing.py`: Lógica de roteamento e Trie.
- `http.py`: Classes Request e Response.
- `middleware.py`: Middlewares padrão (Logger, CORS).
- `utils.py`: Utilitários diversos.
- `websocket.py`: Implementação do protocolo WebSocket.

## Quick Start

```python
import uasyncio as asyncio
from microserver import MicroServer

app = MicroServer(port=80)

@app.get("/")
async def index(req):
    return {"message": "Hello World"}

# Inicia o servidor
asyncio.run(app.run())
```

## Funcionalidades e Uso

### Roteamento Básico
Use decoradores para registrar handlers para métodos HTTP específicos:
```python
@app.get("/status")
async def status(req):
    return "OK"

@app.post("/data")
async def receive_data(req):
    return {"received": True}
```
Métodos suportados: `get`, `post`, `put`, `delete`, `patch`, `options`.

### Rotas Dinâmicas
Capture partes da URL como parâmetros usando `<nome_parametro>`:
```python
@app.get("/users/<user_id>")
async def get_user(req):
    uid = req.path_params.get("user_id")
    return {"id": uid, "name": "User " + uid}

@app.put("/device/<dev_id>/state/<state>")
async def set_state(req):
    dev = req.path_params["dev_id"]
    st = req.path_params["state"]
    return f"Device {dev} set to {st}"
```

### Arquivos Estáticos
Sirva arquivos diretamente do sistema de arquivos (flash):
```python
# Monta /flash/www na URL /static
app.mount_static("/static", "/flash/www")
```
Acessar `http://ip/static/style.css` servirá `/flash/www/style.css`.
*Nota: Protege contra Path Traversal (`..`) automaticamente.*

### WebSockets
Comunicação bidirecional em tempo real:
```python
@app.websocket("/ws")
async def websocket_endpoint(ws):
    await ws.accept() # Opcional se já aceito automaticamente
    await ws.send("Connected!")
    
    while True:
        msg = await ws.receive()
        if msg is None: break # Conexão fechada
        await ws.send(f"Echo: {msg}")
```

### Middleware
Intercepte requisições e respostas globalmente.
```python
from middleware import LoggingMiddleware, CORSMiddleware

# Log de requisições
app.add_middleware(LoggingMiddleware())

# Configuração CORS
app.add_middleware(CORSMiddleware(
    origins="*", 
    methods="GET,POST,PUT,DELETE", 
    headers="Content-Type,Authorization"
))
```

### Request e Response

**Objeto `Request`:**
- `req.method`: Método HTTP (GET, POST...).
- `req.path`: Caminho da URL.
- `req.query_params`: Dicionário de query string (`?id=1` -> `{"id": "1"}`).
- `req.path_params`: Parâmetros de rota dinâmica.
- `req.headers`: Dicionário de headers.
- `req.ip`: Endereço IP do cliente.
- `req.body`: Corpo bruto (bytes).
- `req.json`: Propriedade que faz parse automático do corpo JSON.

**Objeto `Response`:**
```python
from http import Response

# Retorno simples (auto-convertido para JSON ou HTML)
return {"status": "ok"} 

# Resposta customizada
return Response(
    body="Error", 
    status=500, 
    content_type="text/plain"
)
```

### Streaming e Arquivos Grandes
Para economizar memória, use geradores para enviar dados em chunks:
```python
@app.get("/large-data")
async def stream_data(req):
    async def data_generator():
        for i in range(100):
            yield f"Row {i}\n"
            await asyncio.sleep(0.1)
            
    return Response(data_generator(), content_type="text/plain")
```

## Arquitetura Interna

O MicroServer é modularizado para facilitar manutenção e extensão:

- **`microserver.py`**: Gerencia o ciclo de vida do servidor TCP (`uasyncio.start_server`), parseamento inicial HTTP e orquestração de middlewares.
- **`routing.py`**: Implementa a lógica de roteamento usando **Trie (Prefix Tree)**.
  - `_StaticTrie`: Otimizada para rotas fixas.
  - `_RouteTrie`: Suporta wildcards (`<param>`) para rotas dinâmicas.
  - O `Router` verifica sequencialmente: Rotas Exatas -> Cache 404 -> Rotas Estáticas -> Rotas Dinâmicas.
- **`http.py`**: Definições leves de `Request` e `Response` usando `__slots__` para economia de RAM.
- **`websocket.py`**: Implementa o handshake e framing do protocolo WebSocket (RFC 6455).

## Fluxo de Processamento

1. **Conexão**: O servidor aceita uma nova conexão TCP.
2. **Parseamento**: 
   - Lê a primeira linha (Request Line).
   - Lê headers até encontrar linha vazia.
   - Verifica `Content-Length` e lê o corpo (respeitando `max_body_size`).
3. **Upgrade Check**: Se for solicitação de WebSocket, realiza handshake e passa controle para o handler WebSocket.
4. **Construção do Request**: Objeto `Request` é criado.
5. **Roteamento**: 
   - `Router` busca o handler correspondente.
   - Parâmetros de URL são extraídos se houver.
6. **Middleware**: A cadeia de middlewares é executada (LIFO - Last In, First Out para resposta).
7. **Handler**: O handler do usuário é executado.
8. **Response**: O retorno é normalizado para objeto `Response`.
9. **Envio**: Headers e corpo são escritos no socket (com suporte a Chunked Transfer Encoding para generators).
10. **Cleanup**: Conexão é fechada e recursos liberados.

## Melhores Práticas

1. **Memória (RAM)**:
   - Evite ler corpos de requisição gigantes. Mantenha `max_body_size` pequeno.
   - Use streaming (generators) para enviar respostas grandes.
   - Chame `gc.collect()` periodicamente se sua aplicação criar muitos objetos temporários.

2. **Concorrência**:
   - Seus handlers devem ser `async`. Evite chamadas bloqueantes (como `time.sleep` ou I/O pesado síncrono).
   - Use `asyncio.sleep` para pausas.

3. **Produção**:
   - Desative logs de debug (`config={"logging": False}`) para reduzir I/O na serial.
   - Limite `max_conns` baseado nos recursos do seu hardware.

## Exemplos
Verifique a pasta [examples/](examples/) para códigos completos:
- **basic.py**: Hello world e rotas simples.
- **medium.py**: Uso de middlewares, POST com JSON e arquivos estáticos.
- **full.py**: Aplicação completa com conexão Wi-Fi, controle de Hardware (LED) e WebSockets.

## Licença
MIT
