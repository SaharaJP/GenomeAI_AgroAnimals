# Установка GenomeAI AgroAnimals как приложения (Installer v1)

Цель: дать "почти one‑click" установку для демо/пилота без ручных действий с venv.

> Архитектурно: installer/launcher не делает расчётов. Он устанавливает зависимости и поднимает UI/Backend.

## Linux/macOS

1) Распакуйте архив репозитория.
2) В терминале:

```bash
bash installers/linux/install.sh
```

После установки появится команда:

```bash
~/.local/bin/genomeai-agroanimals --open-browser
```

Можно добавить `~/.local/bin` в PATH, либо запускать напрямую.

Также создаётся ярлык:
- Linux: пункт в меню приложений и файл `~/Desktop/GenomeAI AgroAnimals.desktop` (если папка Desktop существует)
- macOS: файл `~/Desktop/GenomeAI AgroAnimals.command` (двойной клик для запуска)

Удаление:

```bash
bash installers/linux/uninstall.sh
```

## Windows 10/11

1) Распакуйте архив репозитория.
2) Запустите PowerShell **от обычного пользователя** и выполните:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
./installers/windows/GenomeAI_AgroAnimals_Setup.ps1
```

После установки создаётся ярлык в меню Пуск и команда:

Дополнительно создаётся ярлык на **Рабочем столе** (best-effort).

```powershell
$env:LOCALAPPDATA\GenomeAI_AgroAnimals\bin\genomeai-agroanimals.cmd
```

Удаление:

```powershell
./installers/windows/GenomeAI_AgroAnimals_Uninstall.ps1
```

## Проверка (для команды)

Не устанавливая ничего, можно проверить команды запуска ("dry-run"):

```bash
python -m genomeai.app_launcher --dry-run
```
