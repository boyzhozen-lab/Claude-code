# ການຕິດຕັ້ງ ແລະ ກຽມຄວາມພ້ອມ

## 1. Claude API key

### ເອົາ key ຢູ່ໃສ

1. ເຂົ້າ **https://platform.claude.com** (ເວັບເກົ່າ `console.anthropic.com` ຈະພາໄປບ່ອນດຽວກັນ)
2. ເຂົ້າສູ່ລະບົບດ້ວຍບັນຊີທີ່ເຄີຍສ້າງ key ໄວ້
3. ໄປທີ່ **Settings → API Keys**
4. ຈະເຫັນລາຍການ key ເກົ່າ, ແຕ່ **ເບິ່ງລະຫັດເຕັມຄືນບໍ່ໄດ້.** ລະບົບສະແດງລະຫັດພຽງເທື່ອດຽວຕອນສ້າງ
5. ຖ້າບໍ່ມີລະຫັດເກັບໄວ້, ໃຫ້ກົດ **Create Key** ສ້າງໃໝ່ ແລະ ຕັ້ງຊື່ເຊັ່ນ `trading-ai`
6. ກັອບປີ້ key (ຂຶ້ນຕົ້ນດ້ວຍ `sk-ant-...`) ແລ້ວເກັບໄວ້ບ່ອນປອດໄພ ເຊັ່ນ password manager
7. ຄວນລຶບ key ເກົ່າທີ່ບໍ່ໃຊ້ແລ້ວ ຫຼື ບໍ່ຮູ້ວ່າເຄີຍເອົາໄປໃສ່ບ່ອນໃດ

### ໝາຍເຫດ

- **API ຄິດເງິນແຍກຈາກ Claude Pro ຫຼື Max.** ຕ້ອງເຕີມເງິນ (credits) ຢູ່ໜ້າ **Billing** ຂອງ platform.claude.com
- ໃນໜ້າ Billing ສາມາດຕັ້ງຂີດຈຳກັດການໃຊ້ຈ່າຍຕໍ່ເດືອນໄດ້. ແນະນຳໃຫ້ຕັ້ງໄວ້
- ຖ້າລະບົບອື່ນທີ່ເຄີຍຕໍ່ໄວ້ຍັງໃຊ້ key ເກົ່າຢູ່, ຢ່າລຶບ key ນັ້ນຈົນກວ່າຈະແນ່ໃຈ

### ⚠️ ຄວາມປອດໄພ

- **ຫ້າມສົ່ງ API key ໃນແຊັດ** (ລວມທັງກັບ Claude)
- **ຫ້າມໃສ່ໃນໂຄດ ຫຼື commit ຂຶ້ນ GitHub.** ຖ້າຫຼຸດຂຶ້ນ, ໃຫ້ລຶບ key ນັ້ນທັນທີ ແລະ ສ້າງໃໝ່
- ໃຫ້ເກັບໄວ້ໃນໄຟລ໌ `.env` ຢູ່ຄອມຂອງເຈົ້າເທົ່ານັ້ນ. `.gitignore` ກັນບໍ່ໃຫ້ໄຟລ໌ນີ້ຂຶ້ນ git ແລ້ວ

```
# .env (ສ້າງເອງຢູ່ໂຟນເດີໂປຣເຈັກໃນຄອມ, ຫ້າມ commit)
ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
```

## 2. ໄລຍະ 1: ຕິດຕັ້ງ ແລະ ໃຊ້ງານໃນ Windows

### 2.1 ຕິດຕັ້ງຄັ້ງທຳອິດ (ເຮັດເທື່ອດຽວ)

1. ຕິດຕັ້ງ **Python 3.11 ຫຼື 3.12** ຈາກ python.org. ຕອນຕິດຕັ້ງໃຫ້ຕິກ **"Add python.exe to PATH"**
2. ຕິດຕັ້ງ **Git for Windows** ຈາກ git-scm.com
3. ເປີດ **Command Prompt** ແລ້ວພິມເທື່ອລະແຖວ:

```bat
cd %USERPROFILE%\Documents
git clone https://github.com/boyzhozen-lab/Claude-code.git trading-ai
cd trading-ai
git checkout claude/trading-ai-ftmo-analysis-4z51eb
python -m venv .venv
.venv\Scripts\activate
pip install -e python
```

### 2.2 ກຽມ MT5

1. ເປີດ MT5 ແລ້ວ login ບັນຊີ **demo** ຂອງ Exness
2. ໄປທີ່ **Tools → Options → Expert Advisors** ແລ້ວຕິກ **Allow algorithmic trading**
3. ໄປທີ່ **Tools → Options → Charts** ແລ້ວຕັ້ງ **Max bars in chart** ເປັນ **Unlimited**, ເພື່ອໃຫ້ດຶງຂໍ້ມູນຍ້ອນຫຼັງໄດ້ຫຼາຍປີ
4. ເປີດ **Market Watch** (Ctrl+M) ແລ້ວກວດຊື່ symbol ແທ້ ເຊັ່ນ `XAUUSDm`. ຖ້າຊື່ບໍ່ກົງກັບ `config/settings.toml`, ໃຫ້ແກ້ໃນໄຟລ໌ນັ້ນ

### 2.3 ຄຳສັ່ງທີ່ໃຊ້ (ເປີດ MT5 ໄວ້ກ່ອນສະເໝີ)

ທຸກເທື່ອທີ່ເປີດ Command Prompt ໃໝ່, ໃຫ້ເຂົ້າໂຟນເດີ ແລະ activate ກ່ອນ:

```bat
cd %USERPROFILE%\Documents\trading-ai
.venv\Scripts\activate
```

| ຄຳສັ່ງ | ເຮັດຫຍັງ |
|---|---|
| `python -m trading_ai check` | ທົດສອບການເຊື່ອມ MT5 ແລະ ກວດຊື່ symbol ທັງໝົດ |
| `python -m trading_ai fetch-bars` | ດຶງຂໍ້ມູນລາຄາຍ້ອນຫຼັງ (ຕັ້ງຄ່າໄວ້ 5 ປີ: M15, H1, D1) ເກັບໄວ້ `data/bars/` |
| `python -m trading_ai validate-bars` | ກວດຂໍ້ມູນ: ຊ່ອງຫວ່າງ, ຂໍ້ມູນຊ້ຳ, ລາຄາຜິດປົກກະຕິ |
| `python -m trading_ai import-history --days 730` | ນຳປະຫວັດການເທຣດທີ່ປິດແລ້ວ ເຂົ້າ journal (`data/journal.db`) ພ້ອມຄິດໄລ່ context |
| `python -m trading_ai stats` | ສະຫຼຸບຜົນ: win rate, profit factor, drawdown, ແຍກຕາມ symbol ແລະ session |
| `python -m trading_ai stats --by weekday trend_d1 exit_reason` | ແຍກຕາມມື້, ແນວໂນ້ມ, ວິທີອອກ |

ລຳດັບທີ່ແນະນຳ: `check` → `fetch-bars` → `validate-bars` → `import-history` → `stats`

### 2.4 💡 ວິເຄາະການເທຣດເກົ່າຂອງເຈົ້າເອງ

`import-history` ພຽງແຕ່**ອ່ານ**ປະຫວັດ, ບໍ່ເປີດ ແລະ ບໍ່ປິດອໍເດີໃດໆ. ສະນັ້ນເຈົ້າສາມາດ login MT5 ເຂົ້າ**ບັນຊີຈິງທີ່ເຄີຍເທຣດ**, ແລ້ວແລ່ນ `import-history --days 1500` ເພື່ອນຳການເທຣດເກົ່າທັງໝົດມາວິເຄາະໄດ້. ມັນຈະບອກວ່າເສຍຫຼາຍໃນ session ໃດ, symbol ໃດ, ມື້ໃດ, ຕອນຕະຫຼາດ trend ຫຼື ບໍ່ trend, ແລະ ເສຍຍ້ອນຕີ SL ຫຼື ປິດເອງ. ນີ້ເປັນບົດຮຽນທຳອິດທີ່ມີຄ່າຫຼາຍ.

### 2.5 ໄລຍະ 2: Backtest ແລະ ຈຳລອງການເສັງ

ຕ້ອງແລ່ນ `fetch-bars` ກ່ອນ. ຄຳສັ່ງເຫຼົ່ານີ້ໃຊ້ຂໍ້ມູນໃນຄອມເທົ່ານັ້ນ, ບໍ່ຕ້ອງເປີດ MT5.

| ຄຳສັ່ງ | ເຮັດຫຍັງ |
|---|---|
| `python -m trading_ai backtest --strategy trend_breakout` | ທົດສອບກົນລະຍຸດ A ກັບທຸກ symbol (D1) |
| `python -m trading_ai backtest --strategy rsi2_reversion --symbols SPX500 DOW30 NAS100` | ທົດສອບກົນລະຍຸດ B ກັບ indices |
| `python -m trading_ai backtest --strategy trend_breakout rsi2_reversion --walk-forward` | ທົດສອບແບບ walk-forward: ນັບສະເພາະຜົນໃນຊ່ວງທີ່ບໍ່ໄດ້ໃຊ້ເລືອກ parameter (ຊື່ສັດກວ່າ) |
| `python -m trading_ai challenge --strategy trend_breakout rsi2_reversion --walk-forward` | ຈຳລອງການເສັງ FTMO 10,000 ເທື່ອ ຕໍ່ລະດັບຄວາມສ່ຽງ |
| `python -m trading_ai backtest --strategy london_breakout ny_breakout --walk-forward` | ທົດສອບກົນລະຍຸດ C (Session Breakout, ໃຊ້ຂໍ້ມູນ H1) |
| `python -m trading_ai challenge --strategy trend_breakout rsi2_reversion london_breakout ny_breakout --walk-forward` | ຈຳລອງການເສັງດ້ວຍ portfolio ທຸກກົນລະຍຸດລວມກັນ |

ແຕ່ລະກົນລະຍຸດມີ timeframe ແລະ symbol ຂອງມັນເອງ (A: D1 ທຸກ symbol, B: D1 indices, C: H1 Gold ແລະ Forex, C2: H1 indices ແລະ Gold). ປ່ຽນໄດ້ດ້ວຍ `--timeframe` ແລະ `--symbols`.

**ເວລາໃນກົນລະຍຸດ C ເປັນ UTC.** ເມື່ອເອີຣົບ ຫຼື ອາເມລິກາປ່ຽນເວລາ (DST), session ຈະເລື່ອນ 1 ຊົ່ວໂມງ. ຕອນນີ້ຍັງບໍ່ໄດ້ປັບເລື່ອງນີ້.

**ວິທີອ່ານຕາຕະລາງ `challenge`:**

| ຖັນ | ຄວາມໝາຍ |
|---|---|
| `risk/trade` | % ຂອງທຶນທີ່ສ່ຽງຕໍ່ໄມ້ |
| `P1 pass` | ໂອກາດຜ່ານຮອບ 1 (+10%) |
| `daily fail` / `total fail` | ໂອກາດຕົກຍ້ອນເສຍເກີນ 5% ໃນມື້ດຽວ / ເກີນ 10% ລວມ |
| `no result` | ຜ່ານໄປ 1 ປີແລ້ວ ຍັງບໍ່ຜ່ານ ແລະ ບໍ່ຕົກ (ກົນລະຍຸດຊ້າເກີນ) |
| `median days` | ຈຳນວນມື້ເທຣດ (ຄ່າກາງ) ກ່ອນຜ່ານ |
| `both` | ໂອກາດຜ່ານທັງສອງຮອບ |

ຄວາມສ່ຽງສູງ = ຜ່ານໄວຂຶ້ນ ແຕ່ຕົກງ່າຍຂຶ້ນ. ເລືອກລະດັບທີ່ `both` ສູງ ແລະ `total fail` ຕ່ຳ.

**⚠️ ຂໍ້ຈຳກັດ:**
- ບໍ່ລວມຄ່າ swap (ຄ່າຖືອໍເດີຂ້າມຄືນ)
- ຄ່າໃຊ້ຈ່າຍໃນ `[costs]` ຂອງ config ເປັນຄ່າປະມານ, ຄວນແກ້ໃຫ້ກົງກັບບັນຊີແທ້
- ການຈຳລອງກວດກົດດ້ວຍ P&L ທີ່ປິດແລ້ວຕອນທ້າຍມື້; ຂອງແທ້ນັບ floating ນຳ, ສະນັ້ນຜົນແທ້ຈະຍາກກວ່ານີ້ເລັກນ້ອຍ
- Backtest ດີ ບໍ່ໄດ້ຮັບປະກັນອະນາຄົດ. ຕ້ອງ forward test ໃນ demo ກ່ອນສະເໝີ

ຜົນ backtest ທຸກໄມ້ຖືກບັນທຶກໄວ້ໃນ `reports/` (ເປີດດ້ວຍ Excel ໄດ້).

### 2.6 ໄລຍະ 3: RiskGuard EA (ໂຕຄຸມຄວາມສ່ຽງ)

RiskGuard ແມ່ນ EA ທີ່**ບໍ່ເປີດອໍເດີເອງ.** ມັນເຝົ້າທຸກອໍເດີໃນບັນຊີ, ທັງທີ່ເທຣດມື ແລະ ທີ່ EA ເປີດ, ແລ້ວບັງຄັບກົດດັ່ງນີ້:

| ກົດ | ຄ່າເລີ່ມຕົ້ນ | ເມື່ອລະເມີດ |
|---|---|---|
| ເສຍໃນມື້ດຽວ | 3% ຂອງທຶນເລີ່ມຕົ້ນ | ປິດທຸກອໍເດີ + ບລັອກຈົນຮອດມື້ໃໝ່ |
| ເສຍລວມ | 7% ຂອງທຶນເລີ່ມຕົ້ນ | ປິດທຸກອໍເດີ + ບລັອກຖາວອນ (ປົດໄດ້ດ້ວຍມືເທົ່ານັ້ນ) |
| ຕ້ອງມີ Stop Loss | ພາຍໃນ 60 ວິນາທີ | ປິດອໍເດີທີ່ບໍ່ມີ SL |
| ຄວາມສ່ຽງລວມຂອງອໍເດີທີ່ເປີດຢູ່ | 1.5% | ປິດອໍເດີໃໝ່ລ່າສຸດ |
| Kill switch | `KILL_close_everything.bat` | ປິດທຸກອໍເດີທັນທີ + ບລັອກ |

**ວິທີຕິດຕັ້ງ:**
1. Double-click **`5_install_riskguard.bat`**. ມັນຈະ copy ແລະ compile EA ໃຫ້ອັດຕະໂນມັດ
2. ໃນ MT5 ເປີດ **Navigator** (Ctrl+N) → **Expert Advisors → TradingAI → RiskGuard**. ຖ້າບໍ່ເຫັນ, ຄລິກຂວາ → Refresh
3. ລາກ RiskGuard ໃສ່ **chart ໃດກໍໄດ້ 1 chart**. ໃນແທັບ Inputs ປັບຄ່າໄດ້, ແລ້ວກົດ OK
4. ກວດວ່າປຸ່ມ **Algo Trading** ຢູ່ແຖບເທິງເປັນສີຂຽວ
5. ມຸມຊ້າຍເທິງຂອງ chart ຈະສະແດງ `RiskGuard [OK]` ພ້ອມ P&L ຂອງມື້

**ສຳລັບ FTMO ແທ້:** ຕັ້ງ `InpInitialBalance` = ຂະໜາດບັນຊີ (ເຊັ່ນ 10000). ຮັກສາ `InpDailyLossPct = 3` ໄວ້, ເພື່ອເຫຼືອ 2% ເປັນ buffer ກ່ອນເສັ້ນ 5% ຂອງ FTMO.

**ແຈ້ງເຕືອນເຂົ້າໂທລະສັບ:** ຕິດຕັ້ງແອັບ MetaTrader 5 ໃນໂທລະສັບ → Settings → Messages ເພື່ອເອົາ **MetaQuotes ID**. ຈາກນັ້ນໃນ MT5 ຄອມໄປທີ່ Tools → Options → Notifications → ຕິກ Enable ແລ້ວໃສ່ ID.

**ທົດລອງໃນ demo:** ເປີດອໍເດີ 0.01 lot ໂດຍບໍ່ໃສ່ SL, ພາຍໃນ 1 ນາທີ RiskGuard ຄວນປິດມັນ. ລອງ `KILL_close_everything.bat` ແລ້ວ `resume_trading.bat` ກໍໄດ້.

### 2.7 RSI2Reversion EA (ກົນລະຍຸດ B) ສຳລັບ forward test ໃນ demo

EA ນີ້ເທຣດຕາມກົດດຽວກັບ backtest ທຸກຢ່າງ: ເບິ່ງແທ່ງ D1 ທີ່ປິດແລ້ວ ແລະ ເຂົ້າອໍເດີຫຼັງແທ່ງໃໝ່ເປີດ. ມັນຊື້ຢ່າງດຽວ, SL = 3 ATR, ອອກເມື່ອລາຄາປິດເໜືອ SMA5 ຫຼື ຖືຄົບ 10 ມື້.

1. Double-click **`5_install_riskguard.bat`** ອີກຮອບ. ມັນຈະ install ແລະ compile ທັງ RiskGuard ແລະ RSI2Reversion
2. ເປີດ chart **US500m D1** (ຫຼື chart ໃດກໍໄດ້, ແຕ່ຕ້ອງເປັນ chart ທີ່ບໍ່ມີ RiskGuard ຢູ່)
3. ລາກ **TradingAI → RSI2Reversion** ໃສ່ chart ນັ້ນ. ຄ່າເລີ່ມຕົ້ນແມ່ນ `US500m,USTECm,US30m` ແລະ ສ່ຽງ 0.5% ຕໍ່ໄມ້. EA ໂຕດຽວເທຣດທັງ 3 symbol
4. ໃນ RiskGuard ຕັ້ງ **`InpMaxOpenRiskPct = 1.6`**, ເພາະ 3 ໄມ້ × 0.5% = 1.5%. ຖ້າບໍ່ປັບ, RiskGuard ອາດປິດອໍເດີທີ 3
5. ມຸມຊ້າຍເທິງຂອງ chart ຈະສະແດງ RSI(2) ຂອງແຕ່ລະ symbol ແລະ ສະຖານະ

**ຢ່າແຕະອໍເດີຂອງ EA ດ້ວຍມື.** ເປົ້າໝາຍຂອງ forward test ແມ່ນເບິ່ງວ່າຜົນຈິງກົງກັບ backtest ບໍ່. ສັນຍານເກີດບໍ່ເລື້ອຍ (ປະມານ 1 ໄມ້ຕໍ່ອາທິດ ລວມ 3 symbol), ສະນັ້ນອາດຫຼາຍມື້ບໍ່ມີອໍເດີເລີຍ ເຊິ່ງເປັນເລື່ອງປົກກະຕິ.

**ທຸກທ້າຍອາທິດ:** double-click **`weekly_check.bat`** (ເປີດ MT5 ໄວ້ກ່ອນ) ແລ້ວສົ່ງ `reports\weekly_check.txt` ໃຫ້ Claude. ມັນຈະທຽບທຸກໄມ້ຂອງ EA ກັບສັນຍານ backtest ໃນມື້ດຽວກັນ:

| ສະຖານະ | ຄວາມໝາຍ |
|---|---|
| `matched` | EA ເທຣດຕາມ backtest ✅ ພ້ອມສະແດງ slippage ຕອນເຂົ້າ (R) ແລະ ມື້ທີ່ອອກ |
| `missed_by_ea` | backtest ມີສັນຍານ ແຕ່ EA ບໍ່ເຂົ້າ (MT5 ປິດ? Algo Trading ປິດ?) |
| `extra_live` | EA ຫຼື ມືເຂົ້າອໍເດີທີ່ backtest ບໍ່ມີ, ຕ້ອງກວດ |
| `still_open` | ໄມ້ທີ່ຍັງເປີດຢູ່ |

### 2.8 ທົດສອບ EA ຕົວຈິງໃນ MT5 Strategy Tester (tick ແທ້)

ໃຊ້ວິທີນີ້ເມື່ອຜົນຂອງ EA ຂຶ້ນກັບສິ່ງທີ່ເກີດຂຶ້ນພາຍໃນແທ່ງທຽນ ເຊັ່ນ trailing stop ແຄບໆ. Backtest ດ້ວຍ Python ເຫັນພຽງ high/low ຂອງແທ່ງ, ແຕ່ Strategy Tester ໃຊ້ tick ແທ້ຂອງໂບຣກເກີ.

1. ໃນ MT5 ກົດ **Ctrl+R** ເພື່ອເປີດ Strategy Tester
2. ຕັ້ງຄ່າ:
   - **Expert:** EA ທີ່ຈະທົດສອບ (ເຊັ່ນ USTEC_ORB_EA_v1.6)
   - **Symbol:** USTECm, **Timeframe:** M5
   - **Date:** Custom period, 2021.10.01 → ມື້ນີ້
   - **Modelling:** **Every tick based on real ticks** ⚠️ ສຳຄັນທີ່ສຸດ
   - **Deposit:** 10000 USD, **Leverage:** 1:100
3. ກົດ **Start** ແລະ ລໍຖ້າ. ຄັ້ງທຳອິດຕ້ອງດາວໂຫຼດ tick ຫຼາຍ GB, ອາດໃຊ້ເວລາເປັນຊົ່ວໂມງ
4. ໄປແທັບ **Backtest** (ຜົນສະຫຼຸບ), ຄລິກຂວາ → **Report → HTML** ແລ້ວບັນທຶກ
5. ສົ່ງໄຟລ໌ report ນັ້ນ ຫຼື capture ໜ້າຈໍຜົນສະຫຼຸບໃຫ້ Claude

### 2.9 ບັນຫາທີ່ພົບເລື້ອຍ

| ຂໍ້ຄວາມ | ວິທີແກ້ |
|---|---|
| `Could not connect to MT5` | ເປີດ MT5 ແລະ login ກ່ອນ. ຖ້າມີ MT5 ຫຼາຍໂຕ, ໃສ່ `terminal_path` ໃນ config |
| `Symbol 'XXX' not found` | ແກ້ຊື່ໃນ `[symbols]` ຂອງ `config/settings.toml` ໃຫ້ກົງກັບ Market Watch |
| ຂໍ້ມູນໄດ້ໜ້ອຍກວ່າ 5 ປີ | ຕັ້ງ Max bars in chart = Unlimited ແລ້ວແລ່ນໃໝ່. ບາງໂບຣກເກີມີຂໍ້ມູນ M15 ຍ້ອນຫຼັງຈຳກັດ |
| `validate-bars` ລາຍງານ gap | ວັນພັກຍາວເປັນເລື່ອງປົກກະຕິ. ຖ້າ gap ເປັນເດືອນ ໃຫ້ແຈ້ງ Claude |

**ໝາຍເຫດ:** ໂຟນເດີ `data/` ບໍ່ຂຶ້ນ GitHub, ເກັບຢູ່ໃນຄອມເຈົ້າເທົ່ານັ້ນ.

## 3. ສິ່ງທີ່ຕ້ອງການໃນໄລຍະຕໍ່ໄປ (ຍັງບໍ່ຕ້ອງເຮັດ)

| ລາຍການ | ໃຊ້ໃນໄລຍະ | ໝາຍເຫດ |
|---|---|---|
| Telegram bot token | 5 | ສ້າງຜ່ານ @BotFather |
| FTMO Free Trial | 6 | ftmo.com |
| VPS Windows | 6 | ໃຫ້ບອດແລ່ນ 24 ຊົ່ວໂມງ |
