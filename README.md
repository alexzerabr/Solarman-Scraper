
# Solarman Scraper

Extrai dados de energia solar do site Solarman em https://home.solarman.cn/ e grava os dados em um banco de dados de séries temporais InfluxDB.

Este script foi criado para uso pessoal, visando a criação de dashboards personalizados no Grafana.

O script em Python foi testado apenas com minha configuração de energia solar; ele pode não funcionar para instalações com várias usinas ou sem bateria. No entanto, o código é relativamente simples de entender e modificar para quem possui experiência em Python.

Observe que as métricas são salvas no InfluxDB com os mesmos nomes de campo usados pela versão antiga da API Solarman, incluindo alguns erros de ortografia, como `useage` em vez de `usage`. Isto não é um bug.

Talvez eu escreva uma nova versão simplificada do script, que armazene dados usando os mesmos nomes de campo da nova API Solarman, mas isso exigirá alguma migração de dados e mudanças nos dashboards do Grafana.

## Pré-requisitos

1. Desenvolvido com Python 3.10, embora possa funcionar com versões >= 3.8.
2. Credenciais para login em https://home.solarman.cn/ com a capacidade de ver os detalhes de sua usina solar em um navegador web.
3. Alguns painéis solares e um pouco de sol ☀️.

## Instalação

1. Instale e execute o InfluxDB: https://docs.influxdata.com/influxdb/v2.1/install/
2. Crie uma organização para o InfluxDB: https://docs.influxdata.com/influxdb/v2.1/organizations/create-org/
3. Crie um token de API para o InfluxDB: https://docs.influxdata.com/influxdb/v2.1/security/tokens/create-token/
4. Crie um arquivo de configuração chamado `.solarman-scraper.yml` no mesmo diretório que o script `solarman-scraper.py` com a seguinte estrutura:

```yaml
solarman:
  login:
    domain: "home.solarman.cn"
    username: "<seu usuário para home.solarman.cn>"
    password: "<sua senha para home.solarman.cn>"
    client_id: <seu client id do solarman> # customerservice@solarmanpv.com envie e-mail solicitando o client_id e secret_id, informe que é para uso pessoal.
    client_secret: <seu client secret>
  plant:
    plant_id: <ID numérico da usina, encontrado na aba 'Plant Info' em https://home.solarman.cn/main.html>

influxdb:
  url: "http://localhost:8086"
  token: "token do influxdb"
  org: "organização do influxdb"
```

5. Instale as dependências:

```bash
python3.10 -m pip install -r requirements.txt
```

## Execução
```bash
python3.10 ./solarman-scraper.py
```

## Dashboards no Grafana

Os dashboards no Grafana criados a partir destes dados podem ser encontrados no diretório [grafana-dashboards](./grafana-dashboards).
As capturas de tela cobrem o período do inverno no Reino Unido. Estou esperando por números significativamente melhores nos meses de verão.

### Energia Solar Hoje
Mostra detalhes da energia solar gerada hoje, juntamente com o consumo de eletricidade e a carga e descarga da bateria.
![Energia Solar Hoje](./grafana-dashboards/Solar%20Power%20Today.png "Energia Solar Hoje")

### Histórico de Energia Solar (Diário)
Mostra totais diários de geração de eletricidade, consumo e exportação.
![Histórico de Energia Solar (Diário)](./grafana-dashboards/Solar%20Power%20History%20(Daily).png "Histórico de Energia Solar (Diário)")

### Finanças da Energia Solar
Exibe informações resumidas sobre energia solar utilizada, além da energia comprada e vendida. O custo aproximado é incluído em cada figura, ajudando a estimar as economias de custos de energia com a instalação solar.

![Finanças da Energia Solar](./grafana-dashboards/Solar%20Finances.png "Finanças da Energia Solar")
