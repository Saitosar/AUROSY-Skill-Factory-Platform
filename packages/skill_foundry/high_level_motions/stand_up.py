import time
from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.go2.sport.sport_client import SportClient

# Инициализация сети для Mac (домен 1, интерфейс lo0)
ChannelFactoryInitialize(1, "lo0")

# Создаем клиента
client = SportClient()
client.SetTimeout(10.0)
client.Init()

print("Отправляем команду встать (RecoveryStand)...")
# Встроенная команда подъема
client.RecoveryStand()

time.sleep(3)
print("Готово. Робот должен стоять.")