# XAU Strategy Lab — Trạm nghiên cứu & tín hiệu XAUUSD

Hệ thống tự động backtest, tìm kiếm và theo dõi các chiến lược giao dịch vàng (XAU/USD), chạy trên 10+ năm dữ liệu daily lấy từ layout TradingView **"Nguyên 7"** (OANDA:XAUUSD). Mỗi ngày hệ thống tự cập nhật dữ liệu, chấm điểm lại toàn bộ chiến lược, và đề xuất tín hiệu MUA/BÁN/ĐỨNG NGOÀI cho phiên tiếp theo.

**Dashboard trực tiếp (Artifact):** https://claude.ai/code/artifact/d11d5d0a-d454-4b17-a935-50929df40caf

> ⚠️ **Miễn trừ trách nhiệm:** Đây là công cụ nghiên cứu định lượng cá nhân, không phải khuyến nghị đầu tư. Hiệu suất quá khứ (backtest) không đảm bảo kết quả tương lai. Người dùng tự chịu trách nhiệm với mọi quyết định giao dịch.

## Nguồn dữ liệu

Toàn bộ dữ liệu giá (`data/xauusd_daily.csv`, 3,110 phiên, 2014-08-20 → 2026-09-03) được xuất trực tiếp từ tính năng **"Download chart data"** có sẵn của TradingView, trên chính layout **"Nguyên 7"** của người dùng (https://www.tradingview.com/chart/eV72iquP/). Đây là nguồn dữ liệu **duy nhất** được dùng cho toàn hệ thống — không dùng Yahoo Finance hay API giá nào khác, đúng theo yêu cầu ban đầu.

## Hệ thống hoạt động thế nào

1. **Tìm kiếm chiến lược (`src/backtest_engine.py`)** — 9 họ chiến lược kinh điển (SMA/EMA Crossover, RSI Mean Reversion, MACD Crossover, Bollinger Breakout/Mean Reversion, Donchian Breakout, ATR Trend kiểu Keltner, Momentum), tổng cộng 77 biến thể tham số. Dữ liệu được chia **70% train / 30% test theo thời gian** (không xáy trộn, tránh nhìn trước tương lai). Mỗi biến thể được chấm điểm trên tập test bằng hàm kết hợp CAGR, drawdown, Sharpe, số lệnh tối thiểu.

2. **Mô phỏng "thử sai rồi đổi" (`src/adaptive_selector.py`)** — walk-forward: cứ mỗi quý, hệ thống chỉ nhìn dữ liệu 2 năm gần nhất (không nhìn tương lai), chọn lại chiến lược đang tốt nhất trong cửa sổ đó rồi áp dụng cho quý kế tiếp. Nếu một phương pháp không còn hiệu quả, hệ thống tự động **chuyển sang phương pháp khác** — đúng yêu cầu ban đầu. Kết quả (kể cả khi kém hơn kỳ vọng) được trình bày minh bạch, không che giấu.

3. **Sinh kết quả (`src/generate_results.py`, `src/engine_full.py`)** — chạy toàn bộ pipeline trên, xuất `results.json` gồm bảng xếp hạng, đường vốn (equity curve), lịch sử walk-forward, và tín hiệu sống mới nhất.

4. **Dashboard (`dashboard/`)** — trang HTML một file, hiển thị bảng xếp hạng chiến lược, biểu đồ equity, lịch sử tín hiệu, và tín hiệu khuyến nghị cho hôm nay. Dữ liệu "sống" được lưu trong cơ sở dữ liệu của chính Artifact (collections `price_bars`, `runs`, `signals`) để tác vụ tự động hằng ngày có thể ghi vào mà không cần máy chủ riêng.

5. **Tác vụ tự động hằng ngày (`automation/daily_job_prompt.txt`)** — prompt đầy đủ được lên lịch chạy mỗi ngày: đọc dữ liệu giá đã lưu → thử lấy phiên giá mới nhất từ TradingView (không tải file, chỉ đọc bảng) → chạy lại toàn bộ engine → ghi kết quả + tín hiệu mới vào database của dashboard. Nếu không lấy được dữ liệu mới, tác vụ dừng và báo lỗi thay vì dùng nguồn dữ liệu khác.

## Kết quả hiện tại (chạy gần nhất: 2026-09-03)

Chiến lược tốt nhất trên tập test: **Bollinger Breakout (n=14, k=2.0)**

| Chỉ số | Tập test (30% gần nhất) | Toàn bộ 10 năm |
|---|---|---|
| Số lệnh | 19 | 68 |
| Tổng lợi nhuận | +87.99% | +66.05% |
| CAGR | 18.59% | 4.19% |
| Max drawdown | -17.74% | -45.43% |
| Win rate | 36.84% | 42.65% |
| Profit factor | 3.17 | 1.52 |
| Sharpe | 0.97 | 0.34 |

**Tín hiệu mới nhất:** MUA (Long) — tính đến 2026-09-03, giá đóng cửa 4,468.21.

**Mô phỏng walk-forward (42 quý, 25 lần đổi chiến lược):** lợi nhuận tích lũy -7.11% — thấp hơn hẳn chiến lược tĩnh tốt nhất, cho thấy việc đổi chiến lược liên tục theo quý không tự động tốt hơn; con số này được giữ nguyên trong dashboard để minh bạch, không chỉ chọn hiển thị kết quả đẹp.

Chi phí giao dịch giả định: 5 bps (0.05%) mỗi lệnh, đã trừ vào toàn bộ kết quả trên.

## Cấu trúc thư mục

```
├── data/                   # Dữ liệu giá gốc từ TradingView (layout "Nguyên 7")
│   ├── xauusd_daily.csv    # Nguồn chính — daily, 2014-08-20 → nay
│   └── xauusd_4h.csv       # Dữ liệu 4h bổ sung (~1 năm), không dùng làm nguồn chính
├── src/                    # Engine backtest + walk-forward
│   ├── backtest_engine.py
│   ├── adaptive_selector.py
│   ├── generate_results.py
│   ├── build_seed.py
│   └── engine_full.py      # Bản gộp 1 file, dùng cho tác vụ tự động hằng ngày
├── results/                # Kết quả đã sinh (results.json + các bản seed cho dashboard)
├── dashboard/               # Dashboard HTML (template + bản đã build)
├── automation/              # Prompt đầy đủ của tác vụ lên lịch hằng ngày
└── docs/
```

## Chạy lại cục bộ

```bash
pip install -r requirements.txt
cd src
python generate_results.py   # đọc ../data/xauusd_daily.csv, ghi results.json
python build_seed.py         # sinh dữ liệu seed để nhúng vào dashboard
```

## Giấy phép

MIT — xem [LICENSE](LICENSE).
