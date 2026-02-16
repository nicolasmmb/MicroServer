"""
SSE Dashboard Example - Vending Machine
Demonstra Server-Sent Events para atualização em tempo real

Acesse: http://192.168.1.100/
"""

import time
from http import Response

import uasyncio as asyncio
import ujson

from microserver import MicroServer

app = MicroServer(port=80)


# Estado global da vending machine
class VendingState:
    def __init__(self):
        self.sales_today = 0
        self.total_revenue = 0.0
        self.products_sold = []
        self.stock = {"Coca-Cola": 10, "Água": 15, "Chips": 8, "Chocolate": 12}
        self.last_sale = None
        self.start_time = time.time()

    def sell(self, product, price):
        """Registra venda de produto"""
        if product in self.stock and self.stock[product] > 0:
            self.sales_today += 1
            self.total_revenue += price
            self.stock[product] -= 1
            self.last_sale = {
                "product": product,
                "price": price,
                "timestamp": time.time(),
            }
            self.products_sold.append(self.last_sale)
            return True
        return False

    def get_stats(self):
        """Retorna estatísticas atuais"""
        return {
            "sales_today": self.sales_today,
            "total_revenue": round(self.total_revenue, 2),
            "stock": self.stock,
            "last_sale": self.last_sale,
            "uptime": int(time.time() - self.start_time),
            "timestamp": time.time(),
        }


state = VendingState()


@app.get("/")
async def index(req):
    """Dashboard HTML com EventSource (SSE)"""
    html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vending Machine Dashboard - SSE</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        h1 {
            color: white;
            text-align: center;
            margin-bottom: 10px;
            font-size: 2.5em;
        }

        .status {
            text-align: center;
            color: white;
            margin-bottom: 30px;
            font-size: 1.2em;
        }

        .status.online {
            color: #4CAF50;
        }

        .status.offline {
            color: #f44336;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }

        .card {
            background: white;
            border-radius: 12px;
            padding: 25px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            transition: transform 0.3s;
        }

        .card:hover {
            transform: translateY(-5px);
        }

        .card-title {
            font-size: 0.9em;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 10px;
        }

        .card-value {
            font-size: 3em;
            font-weight: bold;
            color: #667eea;
            margin: 10px 0;
        }

        .card-subtitle {
            font-size: 0.9em;
            color: #999;
        }

        .stock-list {
            list-style: none;
        }

        .stock-item {
            display: flex;
            justify-content: space-between;
            padding: 12px 0;
            border-bottom: 1px solid #eee;
            font-size: 1.1em;
        }

        .stock-item:last-child {
            border-bottom: none;
        }

        .stock-qty {
            font-weight: bold;
        }

        .stock-qty.low {
            color: #f44336;
        }

        .stock-qty.ok {
            color: #4CAF50;
        }

        .last-sale {
            font-size: 1.1em;
            line-height: 1.6;
        }

        .last-sale-empty {
            color: #999;
            font-style: italic;
        }

        .timestamp {
            color: #999;
            font-size: 0.9em;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        .updating {
            animation: pulse 1s ease-in-out infinite;
        }

        .controls {
            background: white;
            border-radius: 12px;
            padding: 25px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }

        .btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 6px;
            font-size: 1em;
            cursor: pointer;
            margin: 5px;
            transition: background 0.3s;
        }

        .btn:hover {
            background: #5568d3;
        }

        .btn:active {
            transform: scale(0.98);
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🥤 Vending Machine Dashboard</h1>
        <div class="status" id="status">● Conectando...</div>

        <div class="grid">
            <div class="card">
                <div class="card-title">Vendas Hoje</div>
                <div class="card-value" id="sales">0</div>
                <div class="card-subtitle">Total de transações</div>
            </div>

            <div class="card">
                <div class="card-title">Faturamento</div>
                <div class="card-value" id="revenue">R$ 0,00</div>
                <div class="card-subtitle">Receita total hoje</div>
            </div>

            <div class="card">
                <div class="card-title">Uptime</div>
                <div class="card-value" id="uptime">0s</div>
                <div class="card-subtitle">Tempo online</div>
            </div>
        </div>

        <div class="grid">
            <div class="card">
                <div class="card-title">Última Venda</div>
                <div class="last-sale" id="last-sale">
                    <div class="last-sale-empty">Nenhuma venda ainda</div>
                </div>
            </div>

            <div class="card">
                <div class="card-title">Estoque</div>
                <ul class="stock-list" id="stock"></ul>
            </div>
        </div>

        <div class="controls">
            <div class="card-title">Simular Vendas (Teste)</div>
            <button class="btn" onclick="simulateSale('Coca-Cola', 5.00)">Vender Coca-Cola</button>
            <button class="btn" onclick="simulateSale('Água', 3.00)">Vender Água</button>
            <button class="btn" onclick="simulateSale('Chips', 4.50)">Vender Chips</button>
            <button class="btn" onclick="simulateSale('Chocolate', 6.00)">Vender Chocolate</button>
        </div>
    </div>

    <script>
        // Conectar ao endpoint SSE
        const eventSource = new EventSource('/api/events');

        eventSource.onopen = function() {
            document.getElementById('status').textContent = '● Conectado (SSE)';
            document.getElementById('status').className = 'status online';
        };

        eventSource.onerror = function() {
            document.getElementById('status').textContent = '● Desconectado';
            document.getElementById('status').className = 'status offline';
        };

        eventSource.onmessage = function(event) {
            const data = JSON.parse(event.data);
            updateDashboard(data);
        };

        function updateDashboard(data) {
            // Vendas
            document.getElementById('sales').textContent = data.sales_today;

            // Faturamento
            document.getElementById('revenue').textContent =
                'R$ ' + data.total_revenue.toFixed(2);

            // Uptime
            const uptime = formatUptime(data.uptime);
            document.getElementById('uptime').textContent = uptime;

            // Última venda
            const lastSaleDiv = document.getElementById('last-sale');
            if (data.last_sale) {
                const sale = data.last_sale;
                const time = new Date(sale.timestamp * 1000).toLocaleTimeString();
                lastSaleDiv.innerHTML = `
                    <div><strong>${sale.product}</strong></div>
                    <div>R$ ${sale.price.toFixed(2)}</div>
                    <div class="timestamp">${time}</div>
                `;
                // Efeito de pulso em nova venda
                lastSaleDiv.classList.add('updating');
                setTimeout(() => lastSaleDiv.classList.remove('updating'), 1000);
            } else {
                lastSaleDiv.innerHTML = '<div class="last-sale-empty">Nenhuma venda ainda</div>';
            }

            // Estoque
            const stockList = document.getElementById('stock');
            stockList.innerHTML = '';
            for (let [product, qty] of Object.entries(data.stock)) {
                const li = document.createElement('li');
                li.className = 'stock-item';

                const qtyClass = qty < 5 ? 'low' : 'ok';

                li.innerHTML = `
                    <span>${product}</span>
                    <span class="stock-qty ${qtyClass}">${qty} un.</span>
                `;
                stockList.appendChild(li);
            }
        }

        function formatUptime(seconds) {
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            const secs = seconds % 60;

            if (hours > 0) {
                return `${hours}h ${minutes}m`;
            } else if (minutes > 0) {
                return `${minutes}m ${secs}s`;
            } else {
                return `${secs}s`;
            }
        }

        async function simulateSale(product, price) {
            try {
                const response = await fetch('/api/sell', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({product, price})
                });

                const result = await response.json();

                if (!result.success) {
                    alert(result.message || 'Produto fora de estoque');
                }
            } catch (error) {
                console.error('Erro ao vender:', error);
            }
        }
    </script>
</body>
</html>
    """
    return Response.html(html)


@app.get("/api/events")
async def sse_events(req):
    """
    Endpoint SSE - envia atualizações em tempo real
    Cliente conecta com: new EventSource('/api/events')
    """

    async def event_stream():
        """Generator que yielda eventos SSE"""
        while True:
            # Pegar estatísticas atuais
            stats = state.get_stats()

            yield f"data: {ujson.dumps(stats)}\n\n".encode()

            await asyncio.sleep(1)

    return Response.sse(event_stream())


@app.post("/api/sell")
async def sell_product(req):
    """API para registrar venda (simulação ou real)"""
    try:
        data = req.json
        product = data.get("product")
        price = data.get("price", 0.0)

        success = state.sell(product, price)

        if success:
            print(f"✅ Venda: {product} - R$ {price:.2f}")
            return Response.json({"success": True, "message": f"{product} vendido!"})
        else:
            return Response.json(
                {"success": False, "message": f"{product} fora de estoque"}, status=400
            )

    except Exception as e:
        return Response.error(str(e), 500)


@app.get("/api/stats")
async def get_stats(req):
    """API REST para pegar estatísticas (sem SSE)"""
    return Response.json(state.get_stats())


async def auto_sales_simulator():
    """
    Task em background que simula vendas automáticas
    Útil para demonstração/testes
    """
    import urandom

    products = [
        ("Coca-Cola", 5.00),
        ("Água", 3.00),
        ("Chips", 4.50),
        ("Chocolate", 6.00),
    ]

    await asyncio.sleep(5)

    while True:
        await asyncio.sleep(urandom.randint(5, 15))

        product, price = products[urandom.randint(0, len(products) - 1)]

        if state.sell(product, price):
            print(f"🛒 Venda automática: {product} - R$ {price:.2f}")


async def main():
    print("=" * 60)
    print("🚀 SSE Dashboard - Vending Machine")
    print("=" * 60)
    print()
    print("📊 Dashboard: http://192.168.1.100/")
    print("📡 SSE endpoint: http://192.168.1.100/api/events")
    print("📈 REST API: http://192.168.1.100/api/stats")
    print()
    print("💡 Abra o dashboard no browser para ver atualizações em tempo real!")
    print()

    await app.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Servidor encerrado")
