# Painel C6 Empresas - Publicação

## Acesso correto pelo celular

Para funcionar em qualquer celular, seja Wi-Fi, 4G ou 5G, o painel precisa ficar em uma hospedagem web com HTTPS.
Não usar IP local nem rede interna.

## Estrutura de acesso

- `/master`: acesso Master para importar os arquivos.
- `/banco`: acesso Banco/Monitor somente leitura.

## Usuários

Definir em variáveis de ambiente da hospedagem:

- `MASTER_USER`
- `MASTER_PASS`
- `MONITOR_USER`
- `MONITOR_PASS`

## Hospedagem recomendada

Usar um serviço web pago e sempre ativo, como Render Starter ou equivalente.
Não usar plano gratuito se o objetivo é evitar pausa, lentidão ao abrir ou instabilidade por hibernação.

## Comando de build

```bash
pip install -r requirements.txt
```

## Comando de start

```bash
python app_server.py
```

## Arquivos de entrada no Master

- Envios WhatsApp: CSV
- Botões/interações: CSV
- Leads enviados: XLSX
- Visão Cliente: XLSX

Após importar, o painel recalcula os indicadores e a visão Banco passa a mostrar os novos dados.
