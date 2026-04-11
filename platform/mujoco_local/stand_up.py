import time
from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.go2.sport.sport_client import SportClient

# 1. Инициализация сети. 
# ВАЖНО: Указываем DOMAIN_ID = 1 и интерфейс "lo0" (как в твоем config.py)
ChannelFactoryInitialize(1, "lo0")

# 2. Создаем клиента
client = SportClient()
client.SetTimeout(10.0)
client.Init()

print("Отправляем команду встать (RecoveryStand)...")
# Встроенная команда подъема из любого положения
client.RecoveryStand()

time.sleep(3)
print("Готово. Робот должен стоять.")