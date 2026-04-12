# Vast.ai GPU Training Guide

Руководство по развертыванию RL обучения на [Vast.ai](https://vast.ai) для Unitree G1.

## Требования

- Аккаунт на Vast.ai с балансом ($5+ рекомендуется)
- SSH ключ добавлен в Vast.ai Settings → Keys
- Локально: `vastai` CLI (опционально)

## Выбор инстанса

### Рекомендуемая конфигурация

| Параметр | Значение |
|----------|----------|
| GPU | RTX 4090 (24GB VRAM) |
| CUDA | 12.x |
| RAM | 32GB+ |
| Disk | 100GB |
| Network | 1Gbps+ |

### Поиск инстанса

На [cloud.vast.ai](https://cloud.vast.ai):

1. Фильтры:
   - GPU: RTX 4090
   - CUDA: 12.0+
   - Disk Space: 100GB+
   
2. Сортировка по DLP/$/hr (эффективность)

3. Выбирайте verified datacenter для стабильности

## Создание инстанса

### Через веб-интерфейс

1. Выберите инстанс
2. Template: `pytorch/pytorch:2.4.0-cuda12.4-cudnn9-devel`
3. Disk: 100GB
4. Enable: SSH, Jupyter
5. Click "Rent"

### Через CLI

```bash
# Установка CLI
pip install vastai

# Поиск инстансов
vastai search offers 'gpu_name=RTX_4090 cuda_vers>=12.0 disk_space>=100'

# Создание инстанса
vastai create instance <OFFER_ID> \
  --image pytorch/pytorch:2.4.0-cuda12.4-cudnn9-devel \
  --env '-e MUJOCO_GL="egl" -e XLA_FLAGS="--xla_gpu_triton_gemm_any=true"' \
  --disk 100 \
  --jupyter --ssh --direct
```

## Настройка окружения

### 1. SSH подключение

```bash
# Получить SSH команду из dashboard или:
vastai ssh-url <INSTANCE_ID>

# Подключение
ssh -p <PORT> root@<IP>
```

### 2. Запуск setup скрипта

```bash
cd /workspace

# Скачать setup скрипт
wget https://raw.githubusercontent.com/YOUR_ORG/AUROSY_creators_factory_platform/main/vast_training/setup_vast.sh

# Запустить (PyTorch режим)
bash setup_vast.sh --pytorch

# Или JAX режим для MuJoCo Playground
bash setup_vast.sh --jax
```

### 3. Проверка установки

```bash
python -c "import torch; print(f'PyTorch: {torch.__version__}, CUDA: {torch.cuda.is_available()}')"
python -c "import mujoco; print(f'MuJoCo: {mujoco.__version__}')"
python -c "import pinocchio; print('Pinocchio: OK')"
```

## Загрузка данных

### Через SCP

```bash
# С локальной машины
scp -P <PORT> reference_trajectory.json root@<IP>:/workspace/data/
scp -P <PORT> scene_29dof.xml root@<IP>:/workspace/data/
```

### Через Syncthing (для больших файлов)

Vast.ai инстансы поддерживают Syncthing на порту 8384.

### Через Git

```bash
# На инстансе
git clone https://github.com/YOUR_ORG/AUROSY_creators_factory_platform.git /workspace/platform
```

## Запуск обучения

### Использование tmux (рекомендуется)

```bash
# Создать сессию
tmux new -s train

# Запустить обучение
python /workspace/platform/vast_training/train_cortex.py \
  --reference /workspace/data/reference_trajectory.json \
  --mjcf /workspace/data/scene_29dof.xml \
  --output /workspace/output \
  --timesteps 100000

# Отсоединиться: Ctrl+B, затем D
# Присоединиться обратно: tmux attach -t train
```

### Мониторинг

```bash
# GPU utilization
watch -n 1 nvidia-smi

# TensorBoard (в отдельном терминале)
tensorboard --logdir /workspace/output --port 6006 --bind_all
```

TensorBoard доступен по адресу: `http://<INSTANCE_IP>:6006`

## Скачивание результатов

```bash
# С локальной машины
scp -P <PORT> -r root@<IP>:/workspace/output/run_* ./results/
```

Результаты включают:
- `ppo_G1TrackingEnv.zip` — обученная политика
- `train_run.json` — метаданные обучения
- `metrics.json` — история rewards

## Оценка стоимости

| Конфигурация | Время | Стоимость |
|--------------|-------|-----------|
| RTX 4090, 100k steps (PyTorch) | ~30-60 мин | ~$0.40 |
| RTX 4090, 500k steps (PyTorch) | ~2-3 часа | ~$1.50 |
| RTX 4090, 1M steps (JAX/MJX) | ~30-60 мин | ~$0.40 |
| RTX 3090, 100k steps | ~60-90 мин | ~$0.30 |

## Troubleshooting

### CUDA out of memory

```yaml
# В train_config.yaml уменьшить batch_size
ppo:
  batch_size: 128  # или 64
```

### MuJoCo rendering errors

```bash
export MUJOCO_GL=egl
# или
export MUJOCO_GL=osmesa
```

### SSH connection drops

Используйте `tmux` или `screen`:

```bash
tmux new -s train
# ... запустить обучение ...
# Ctrl+B, D для отсоединения
```

### Slow training

1. Проверьте GPU utilization: `nvidia-smi`
2. Если GPU idle — проблема в CPU-bound коде
3. Для PyTorch: увеличьте `n_steps` в конфиге
4. Для JAX: используйте `jax.vmap` для параллелизации

## Best Practices

1. **Всегда используйте tmux** — SSH может отключиться
2. **Сохраняйте checkpoints часто** — инстанс может быть прерван
3. **Мониторьте через TensorBoard** — ловите проблемы рано
4. **Используйте reserved instances** для длительных задач (до 50% дешевле)
5. **Stop instance когда не используете** — storage charges продолжаются

## Связанные документы

- [04_cortex_pipeline.md](../skill_foundry/04_cortex_pipeline.md) — архитектура Cortex
- [05_cortex_api_reference.md](../skill_foundry/05_cortex_api_reference.md) — API документация
- [vast_training/README.md](../../vast_training/README.md) — quick start
