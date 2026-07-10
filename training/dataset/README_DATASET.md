# Датасет Savr: Eltex MES / Cisco IOS — формат и статус

Файлы подготовлены для передачи в конвейер обучения (Claude Code). Формат — стандартный
conversational JSONL (TRL/ChatML): если целевая схема отличается, конвертация тривиальна —
всё содержимое в `messages`, метаданные рядом на верхнем уровне.

## Файлы

| Файл | Что это |
|---|---|
| `eltex_syslog_batch1.jsonl` | Партия 1: 20 эпизодов интерпретации syslog Eltex MES |
| `cisco_ios_batch2.jsonl` | Партия 2: 8 многоходовых ticket-эпизодов Cisco IOS по алгоритму инженера |
| `vlan_change_batch4.jsonl` | Партия 4: 6 эпизодов смены VLAN (`vlan_changing_CISCO.txt`): штатная смена, стоп-ветки (trunk, VLAN нет на свитче/в аплинке), пост-контроль (ISG deny-all, конфликт sticky) |
| `configs_batch3.jsonl` | Партия 3: 10 config_task-эпизодов по реальным шаблонам (`*_template_*.txt`): настройка access/uplink Cisco+Eltex, кросс-вендор, аудиты, нюанс bpdufilter/bpduguard. Решения инженера: max 1 MAC — стандарт; bpdufilter+bpduguard остаются (модель знает нюанс); Eltex-стандарт минимальный осознанно |
| `CISCO_IOS_troubleshooting_v2.md` | Исправленный алгоритм инженера (источник партии 2 и следующих Cisco-эпизодов) |
| `eltex_syslog_catalog.json` | 463 сообщения из официального «Руководства по сообщениям Syslog» (MES23xx/33xx/35xx/5324), распарсенные по полям — сырьё для массовой генерации следующих партий |
| `ALGORITHM_TEMPLATE.md` | Шаблон описания типовых проблем инженером — источник эпизодов типа "ticket_diagnostics" |

## Политика выполнения команд (зашита в канонический system-промпт, партии 1–2 синхронизированы)

Savr сам выполняет show-команды; из изменений разрешено только удаление sticky MAC
port-security + сопутствующие clear. Всё остальное (`no shutdown`, VLAN и т.д.) —
рекомендация инженеру. Эпизоды cis-tkt-0001 (отказ выполнять no shutdown) и
cis-tkt-0002 (самостоятельное удаление sticky) обучают именно этой границе.

## Паттерн CLI-диалога в ticket_diagnostics

Assistant называет команду (в код-блоке) → следующий user-ход содержит сырой вывод CLI →
assistant интерпретирует. Если конвейер использует tool-calling формат, эти user-ходы
конвертируются в tool-ответы механически.

## Формат эпизода (одна строка JSONL)

```json
{
  "id": "elx-slg-0001",
  "lang": "ru",
  "vendor": "eltex",                      // eltex | cisco
  "device": "MES23xx/33xx/35xx/5324",
  "fw": "4.0.27",
  "source": "mes_log_reference_4.0.27",   // происхождение фактуры
  "type": "syslog_interpretation",        // syslog_interpretation | show_diagnostics | config_task | ticket_diagnostics
  "tags": ["stp", "bpdu-guard"],
  "verified": false,                      // true после доменной проверки инженером
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

- `messages[0]` — всегда один и тот же канонический system-промпт (персона Savr). При
  необходимости заменяется глобально одной операцией.
- Диалоги 2–4 хода, роли строго чередуются, завершает assistant.
- Обучение (loss) — только на репликах assistant (маскировка уже реализована в `train_lora.py`).

## Заземление и верификация

Партия 1 заземлена на официальные PDF Eltex (лежат в этой папке):
формат сообщений, важность, причины и рекомендуемые действия — из log reference;
синтаксис команд (`set interface active`, `show errdisable interfaces`, `show stack links details`,
`show power inline consumption`, `show system sensors` и т.д.) сверен с руководством по
эксплуатации 4.0.27.

Тем не менее **все эпизоды `verified: false` до проверки инженером**. Проверять на:
фактические ошибки в командах, неверные причинно-следственные связи, нереалистичные
сценарии. После проверки — выставить `verified: true`.

## План следующих партий

1. Ещё syslog-эпизоды из каталога (463 сообщения покрыты пока на ~4%).
2. `show_diagnostics` — разбор выводов show-команд (фактура из руководства по эксплуатации).
3. `config_task` — задачи настройки (VLAN, LACP, port security, DHCP snooping...).
4. `ticket_diagnostics` — сценарии из алгоритмов инженера (шаблон `ALGORITHM_TEMPLATE.md`) — самый ценный тип.
5. Cisco IOS (классический) — аналогичные типы.
