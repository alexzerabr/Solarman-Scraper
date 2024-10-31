import os
import json
import time
import yaml
from datetime import datetime, timedelta, date
from hashlib import sha256

import logging
import retry
import requests
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

SOLARMAN_API = 'https://globalapi.solarmanpv.com'

# Configure o caminho do arquivo de log
log_dir = "/tmp/solarman/"
log_file = os.path.join(log_dir, "solarman_api.log")

# Verifica se o diretório de log existe, caso contrário, cria-o
os.makedirs(log_dir, exist_ok=True)

# Configuração do formato de log
FORMAT = '%(asctime)s %(levelname)s [%(name)s] %(message)s'
logging.basicConfig(
    format=FORMAT,
    level=logging.INFO,
    handlers=[
        logging.FileHandler(log_file),  # Grava os logs no arquivo
        logging.StreamHandler()         # Também exibe os logs no console
    ]
)

DAY_DETAIL_FIELDS = {
    'B_left_cap1': 'battery_soc',           # bateria % de carga
    'Pcg_dcg1':    'battery_power',         # potência de carga/descarga da bateria (descarga é negativa)
    'Etdy_cg1':    'daily_charge_energy',
    'Etdy_dcg1':   'daily_discharge_energy',
    'APo_t1':      'power',                 # Potência total de saída AC dos painéis solares
    'PG_Pt1':      'power_grid',            # Potência comprada/vendida (positivo é exportação)
    't_gc_tdy1':   'daily_grid_feed_in',
    'Etdy_pu1':    'daily_grid_purchase',
    'E_Puse_t1':   'power_useage',          # potência total de consumo
}

DAY_SUMMARY_FIELDS = {
    'generation': 'energy',
    'charge': 'energy_batter_in',
    'discharge': 'energy_batter_out',
    'purchase': 'energy_buy',
    'grid': 'energy_sell',
    'consumption': 'energy_useage',
}

SNAPSHOT_POWER_FIELDS = {
    'generationPower': 'power',
    'batteryPower':    'powerBattery',
    'gridPower':       'powerGrid',
    'usePower':        'powerUseage', # sic
    'chargePower':     'chargePower',
    'dischargePower':  'dischargePower',
    'purchasePower':   'powerPurchase'
}


class SolarmanClient:

    logger = logging.getLogger('SolarmanClient')

    def __init__(self, login_config):
        self.headers = {
            "Content-Type": "application/json",
            "User-Agent": "curl"
        }
        self.login_config = login_config
        self.session = requests.session()
        self.auth_headers = self.headers | {"Authorization": f"Bearer {self.login()}"}

    def login(self):
        encoded_password = sha256(self.login_config['password'].encode('utf-8')).hexdigest()
        try:
            r = self.session.post(
                f"{SOLARMAN_API}/account/v1.0/token?appId={self.login_config['client_id']}&language=en",
                headers=self.headers,
                json={
                    'appSecret': self.login_config['client_secret'],
                    'email': self.login_config['email'],
                    'password': encoded_password,
                },
                timeout=60
            )
            r.raise_for_status()
            data = r.json()
            token = data['access_token']
            return token
        except requests.exceptions.HTTPError as e:
            self.logger.error(f"Falha na autenticação: {e}")
            raise
        except json.decoder.JSONDecodeError:
            self.logger.error("Falha na resposta de autenticação: JSON esperado mas outro formato recebido.")
            raise

    @retry.retry(tries=10, delay=1, backoff=2, logger=logger)
    def get_plant_info(self, plant_id):
        try:
            r = self.session.post(
                f"{SOLARMAN_API}/station/v1.0/base?language=en",
                headers=self.auth_headers,
                json={"stationId": plant_id},
                timeout=60
            )
            r.raise_for_status()
            data = r.json()
            return data
        except requests.exceptions.HTTPError as e:
            self.logger.error(f"Erro ao obter informações da planta: {e}")
            raise

    def get_device_info(self, plant_id):
        try:
            r = self.session.post(
                f"{SOLARMAN_API}/station/v1.0/device?language=en",
                headers=self.auth_headers,
                json={"stationId": plant_id},
                timeout=60
            )
            r.raise_for_status()
            data = r.json()
            return data["deviceListItems"]
        except requests.exceptions.HTTPError as e:
            self.logger.error(f"Erro ao obter informações do dispositivo: {e}")
            raise

    @retry.retry(tries=10, delay=1, backoff=2, logger=logger)
    def get_plant_snapshot(self, plant_id):
        try:
            r = self.session.post(
                f"{SOLARMAN_API}/station/v1.0/realTime?language=en",
                headers=self.auth_headers,
                json={"stationId": plant_id},
                timeout=60
            )
            r.raise_for_status()
            data = r.json()
            return data
        except requests.exceptions.HTTPError as e:
            self.logger.error(f"Erro ao obter instantâneo da planta: {e}")
            raise

    @retry.retry(tries=10, delay=1, backoff=2, logger=logger)
    def get_day_data(self, device, day: str):
        try:
            r = self.session.post(
                f"{SOLARMAN_API}/device/v1.0/historical?language=en",
                headers=self.auth_headers,
                json={
                    "deviceId": device["deviceId"],
                    "deviceSn": device["deviceSn"],
                    "startTime": day,
                    "endTime": day,
                    "timeType": 1
                },
                timeout=60
            )
            r.raise_for_status()
            data = r.json()
            return data
        except requests.exceptions.HTTPError as e:
            self.logger.error(f"Erro ao obter dados do dia: {e}")
            raise

    @retry.retry(tries=10, delay=1, backoff=2, logger=logger)
    def get_daily_summary_data(self, device, start_date: str, end_date: str):
        try:
            r = self.session.post(
                f"{SOLARMAN_API}/device/v1.0/historical?language=en",
                headers=self.auth_headers,
                json={
                    "deviceId": device["deviceId"],
                    "deviceSn": device["deviceSn"],
                    "startTime": start_date,
                    "endTime": end_date,
                    "timeType": 2
                },
                timeout=60
            )
            r.raise_for_status()
            data = r.json()
            return data
        except requests.exceptions.HTTPError as e:
            self.logger.error(f"Erro ao obter dados resumidos diários: {e}")
            raise


class InfluxDBWriter:

    logger = logging.getLogger('InfluxDBWriter')

    def __init__(self, influxdb_config):
        self.influxdb_config = influxdb_config
        self.client = InfluxDBClient(**influxdb_config)
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)

    @retry.retry(tries=10, delay=1, logger=logger)
    def write_day_chart_data(self, plant_id, measurement_name, day_data):
        device_sn = day_data["deviceSn"]
        chart_data = day_data["paramDataList"]
        for ts_entry in chart_data:
            data = {d["key"]: (float(d["value"])/1000 if d.get("unit") == 'W' else float(d["value"]))
                    for d in ts_entry["dataList"]
                    if d["key"] in DAY_DETAIL_FIELDS and "value" in d}
            ts = datetime.utcfromtimestamp(int(ts_entry['collectTime']))
            point = Point(measurement_name).tag("plant_id", plant_id).tag("device_sn", device_sn).time(ts, WritePrecision.S)
            for data_key, write_key in DAY_DETAIL_FIELDS.items():
                point.field(write_key, data.get(data_key, 0.0))

            battery_charge_discharge = data.get('Pcg_dcg1', 0.0)
            if battery_charge_discharge > 0:
                point.field('energy_batter_in', battery_charge_discharge)
                point.field('energy_batter_out', 0.0)
            else:
                point.field('energy_batter_in', 0.0)
                point.field('energy_batter_out', battery_charge_discharge)

            grid_power = data.get('PG_Pt1', 0.0)
            if grid_power > 0:
                point.field('power_buy', 0.0)
                point.field('power_sell', grid_power)
            else:
                point.field('power_buy', -grid_power)
                point.field('power_sell', 0.0)

            self.write_api.write("solarman", self.client.org, point)

    @retry.retry(tries=10, delay=1, logger=logger)
    def write_daily_summary_data(self, plant_id, measurement_name, month_data):
        device_sn = month_data["deviceSn"]
        chart_data = month_data["paramDataList"]
        for day_summary in chart_data:
            self.write_day_summary_data(plant_id, device_sn, measurement_name, day_summary)

    @retry.retry(tries=10, delay=1, logger=logger)
    def write_day_summary_data(self, plant_id, device_sn, measurement_name, day_summary):
        date_ts = datetime.fromisoformat(day_summary["collectTime"])
        data = {d["key"]: (float(d["value"])/1000 if d.get("unit") == 'W' else float(d["value"]))
                for d in day_summary["dataList"]
                if d["key"] in DAY_SUMMARY_FIELDS and "value" in d}
        point = Point(measurement_name).tag("plant_id", plant_id).tag("device_sn", device_sn).time(date_ts, WritePrecision.S)
        for data_key, write_key in DAY_SUMMARY_FIELDS.items():
            point.field(write_key, data.get(data_key, 0.0))
        self.write_api.write("solarman", self.client.org, point)

    @retry.retry(tries=10, delay=1, logger=logger)
    def write_plant_snapshot(self, plant_id, measurement_name, plant_snapshot):
        ts = datetime.utcfromtimestamp(int(plant_snapshot['lastUpdateTime']))
        self.logger.info(f"Gravando instantâneo para {ts}")
        point = Point(measurement_name).tag("plant_id", plant_id).time(ts, WritePrecision.S)
        for data_key, write_key in SNAPSHOT_POWER_FIELDS.items():
            value = plant_snapshot.get(data_key) or 0.0
            point.field(write_key, float(value) / 1000.0)  # API antiga usava kW, não W
        self.write_api.write("solarman", self.client.org, point)

    @retry.retry(tries=10, delay=1, logger=logger)
    def write_day_battery_charge_data(self, measurement_name, day_battery_charge_data):
        plant_id = day_battery_charge_data['plantId']
        chart_data = day_battery_charge_data["chartData"]

        minllis = day_battery_charge_data['minllis']

        for epoch_millis, percent in chart_data:
            ts = datetime.utcfromtimestamp(int(epoch_millis) / 1000 - minllis*60)
            point = Point(measurement_name).tag("plant_id", plant_id).time(ts, WritePrecision.S)
            point.field("charge_pc", float(percent))
            self.write_api.write("solarman", self.client.org, point)


class SolarmanScraper:

    logger = logging.getLogger('SolarmanScraper')

    def __init__(self, config):
        self.config = config

        solarman_config = config["solarman"]
        self.solarman = SolarmanClient(solarman_config["login"])
        self.plant_config = dict(solarman_config["plant"])
        self.plant_id = self.plant_config["plant_id"]

        if "timezone" not in self.plant_config.keys():
            plant_info = self.solarman.get_plant_info(self.plant_id)
            self.plant_config["timezone"] = plant_info["region"]["timezone"]

        self.device_list = self.solarman.get_device_info(self.plant_id)
        self.inverters = [d for d in self.device_list if d["deviceType"] == "INVERTER"]

        influxdb_config = config["influxdb"]
        self.influxdb = InfluxDBWriter(influxdb_config)

        # Configurações adicionais para flexibilidade
        self.backfill_days = self.plant_config.get("backfill_days", 7)
        self.snapshot_interval = self.plant_config.get("snapshot_interval", 600)  # padrão 10 minutos

    def process_month(self, date):
        month_start = date.strftime("%Y-%m-01")
        month_end = date.strftime("%Y-%m-%d")
        self.logger.info(f"Processando dados para o mês {month_start}")
        for device in self.inverters:
            month_data = self.solarman.get_daily_summary_data(device, month_start, month_end)
            self.influxdb.write_daily_summary_data(self.plant_id, "solarman_daily_summary", month_data)

    def process_day(self, date):
        day = date.strftime("%Y-%m-%d")
        self.logger.info(f"Processando dados para a data {day}")
        for device in self.inverters:
            day_data = self.solarman.get_day_data(device, day)
            self.influxdb.write_day_chart_data(self.plant_id, "solarman", day_data)
            day_summary_data = self.solarman.get_daily_summary_data(device, day, day)
            self.influxdb.write_daily_summary_data(self.plant_id, "solarman_daily_summary", day_summary_data)

    def process_snapshot(self):
        self.logger.info(f"Processando instantâneo")
        plant_snapshot = self.solarman.get_plant_snapshot(self.plant_id)
        self.influxdb.write_plant_snapshot(self.plant_id, "solarman_power", plant_snapshot)


def daterange(start_date, end_date):
    for n in range(int((end_date - start_date).days)):
        yield start_date + timedelta(n)


def main():
    with open(".solarman-scraper.yml", "r") as yamlfile:
        config = yaml.load(yamlfile, Loader=yaml.FullLoader)
    scraper = SolarmanScraper(config)

    today = date.today()
    scraper.process_month(today)

    for previous_day in range(scraper.backfill_days, 0, -1):
        scraper.process_day(today - timedelta(previous_day))

    while True:
        try:
            scraper.process_snapshot()
            new_today = date.today()

            if new_today != today:
                scraper.process_day(today)
                scraper.process_month(today)
                today = new_today

            scraper.process_day(today)

        except json.decoder.JSONDecodeError:
            scraper.solarman.login()
            raise

        time.sleep(scraper.snapshot_interval)


if __name__ == '__main__':
    main()
