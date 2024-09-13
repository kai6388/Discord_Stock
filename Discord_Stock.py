import discord
import yfinance as yf
import os
import matplotlib.pyplot as plt
import io
import logging
from logging.handlers import TimedRotatingFileHandler
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
from dotenv import load_dotenv

import glob  # 추가: 파일 목록을 가져오기 위한 모듈
import shutil  # 추가: 파일 이동을 위한 모듈
import time  # 추가: 파일의 수정 시간을 확인하기 위한 모듈

# 로깅 설정
class CustomTimedRotatingFileHandler(TimedRotatingFileHandler):
    def __init__(self, *args, **kwargs):
        super(CustomTimedRotatingFileHandler, self).__init__(*args, **kwargs)
        self.total_data_sent = 0  # 하루 동안 전송된 데이터의 총량을 저장

        # 추가: old_log 폴더 경로 설정
        self.old_log_dir = os.path.join(os.path.dirname(self.baseFilename), 'old_log')
        if not os.path.exists(self.old_log_dir):
            os.makedirs(self.old_log_dir)
            logging.info(f"Created old_log directory at {self.old_log_dir}")

    def emit(self, record):
        super(CustomTimedRotatingFileHandler, self).emit(record)
        if hasattr(record, 'data_size'):
            self.total_data_sent += record.data_size

    def doRollover(self):
        # 부모 클래스의 doRollover() 호출로 로그 파일 회전
        super(CustomTimedRotatingFileHandler, self).doRollover()
        # 새로운 로그 파일에 어제 전송한 데이터 총량 기록
        if self.stream:
            self.stream.write(f"어제 전송된 총 데이터 양: {self.total_data_sent} bytes\n")
            self.stream.flush()
        # 데이터 총량 초기화
        self.total_data_sent = 0

        # 추가: 오래된 로그 파일 이동
        self.move_old_logs()

    def move_old_logs(self):
        """2주(14일) 이상된 로그 파일을 old_log 폴더로 이동"""
        log_dir = os.path.dirname(self.baseFilename)
        if not log_dir:
            log_dir = '.'
        # 로그 파일 패턴에 맞는 모든 파일 목록 가져오기
        log_files = glob.glob(os.path.join(log_dir, self.prefix + "*"))
        current_time = time.time()

        for log_file in log_files:
            # 현재 사용 중인 로그 파일은 건너뜀
            if log_file == self.baseFilename:
                continue
            # 파일의 마지막 수정 시간 가져오기
            file_mtime = os.path.getmtime(log_file)
            # 파일이 14일(14 * 86400초)보다 오래되었는지 확인
            if (current_time - file_mtime) > (14 * 86400):
                try:
                    # 파일을 old_log 폴더로 이동
                    shutil.move(log_file, self.old_log_dir)
                    logging.info(f"Moved old log file to {self.old_log_dir}: {log_file}")
                except Exception as e:
                    logging.error(f"Failed to move old log file {log_file}: {e}")

    @property
    def prefix(self):
        """로그 파일의 접두사를 반환"""
        return os.path.basename(self.baseFilename).split('.')[0]

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 핸들러 설정 (매일 자정에 로그 파일 갱신)
handler = CustomTimedRotatingFileHandler('bot.log', when='midnight', interval=1, atTime=datetime.time(20, 0), encoding='utf-8')
handler.suffix = "%Y%m%d"  # 로그 파일명에 날짜 추가
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s:%(message)s'))
logger.addHandler(handler)

# 콘솔 출력 핸들러 추가
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s:%(message)s'))
logger.addHandler(console_handler)

load_dotenv()

# 디스코드 봇 토큰
TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = 1272735912148861011  # 메세지를 보낼 디스코드 채널 ID를 입력하세요

if TOKEN is None:
    logging.error("DISCORD_TOKEN is not set. Check your .env file.")
    raise ValueError("DISCORD_TOKEN is not set. Check your .env file.")

# 인텐트 설정
intents = discord.Intents.default()
intents.message_content = True  # 메시지 내용 인텐트 활성화

# Bot 객체 생성
bot = commands.Bot(command_prefix="!", intents=intents)

# 스케줄러 초기화
scheduler = AsyncIOScheduler()

# 관심 종목 리스트
WATCHLIST_FILE = 'watchlist.txt'

# 관심종목 초기화
watchlist = []


@bot.event
async def on_ready():
    logging.info(f'Logged in as {bot.user}')

    load_watchlist()
    logging.info('Watchlist loaded')

    # 스케줄러 설정
    scheduler.add_job(calculate_ma_scheduled, 'cron', day_of_week='mon-fri', hour=20, minute=15)
    scheduler.add_job(stock_price_notification, 'cron', day_of_week='mon-fri', hour=20, minute=16)
    scheduler.add_job(check_watchlist, 'cron', day_of_week='mon-fri', hour=20, minute=17)
    scheduler.add_job(check_news, 'cron', day_of_week='mon-fri', hour=20, minute=18)
    scheduler.start()
    logging.info('Scheduler started')


# 관심종목 관련 뉴스 출력
async def check_news():
    """관심종목에 대해 최신 뉴스를 체크하여 디스코드로 전송"""
    logging.info('Running check_news')
    messages = []
    current_time = datetime.now()
    one_day_ago = current_time - timedelta(days=1)

    for ticker in watchlist:
        stock = yf.Ticker(ticker)
        news_items = stock.news

        for item in news_items:
            news_time = datetime.utcfromtimestamp(item['providerPublishTime'])
            if news_time > one_day_ago:
                headline = item['title']
                link = item['link']
                messages.append(f"**{ticker}**: {headline}\n링크: {link}")

    if messages:
        combined_message = "\n\n".join(messages)
        channel = bot.get_channel(CHANNEL_ID)
        if channel:
            # Discord 메시지 길이 제한(2000자)을 고려하여 메시지를 분할
            for chunk in [combined_message[i:i+1900] for i in range(0, len(combined_message), 1900)]:
                await channel.send(chunk)
                # 전송한 메시지의 크기를 로깅
                data_size = len(chunk.encode('utf-8'))
                logging.info(f'Sent news message of size {data_size} bytes', extra={'data_size': data_size})
        else:
            logging.error("채널을 찾을 수 없습니다. CHANNEL_ID를 확인하세요.")
    else:
        logging.info('No new news to send')


# 이동평균선 계산 함수
def calculate_moving_averages(data):
    """이동평균선 계산 함수"""
    ma_20 = data['Close'].rolling(window=20).mean().iloc[-1]
    ma_50 = data['Close'].rolling(window=50).mean().iloc[-1]
    ma_100 = data['Close'].rolling(window=100).mean().iloc[-1]
    ma_200 = data['Close'].rolling(window=200).mean().iloc[-1]
    return ma_20, ma_50, ma_100, ma_200


# !MA 명령어를 통해 종목의 MA, 종가를 출력
@bot.command(name='MA')
async def moving_averages(ctx, ticker: str):
    ticker = ticker.upper()
    logging.info(f'Command !MA invoked for ticker: {ticker}')

    # 주식 데이터 가져오기 (1년간)
    data = yf.download(ticker, period='1y')

    if data.empty:
        await ctx.send(f"{ticker}에 대한 데이터를 가져올 수 없습니다.")
        logging.warning(f'No data found for ticker: {ticker}')
        return

    # 종가 및 이동평균선 계산
    latest_close = data['Close'].iloc[-1]
    ma_20, ma_50, ma_100, ma_200 = calculate_moving_averages(data)

    # 출력 내용 생성
    message = (
        f"**{ticker}**의 종가와 이동평균선(MA):\n"
        f"종가: ${latest_close:.2f}\n"
        f"20MA: ${ma_20:.2f}\n"
        f"50MA: ${ma_50:.2f}\n"
        f"100MA: ${ma_100:.2f}\n"
        f"200MA: ${ma_200:.2f}"
    )

    # 디스코드 채널에 결과 전송
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        data_size = len(message.encode('utf-8'))
        await channel.send(message)
        logging.info(f'Sent MA message for ticker: {ticker}, size: {data_size} bytes', extra={'data_size': data_size})
    else:
        logging.error("채널을 찾을 수 없습니다. CHANNEL_ID를 확인하세요.")


@bot.command(name='관심종목추가')
async def add_to_watchlist(ctx, ticker: str):
    ticker = ticker.upper()
    logging.info(f'Command !관심종목추가 invoked for ticker: {ticker}')
    if ticker not in watchlist:
        watchlist.append(ticker)
        save_watchlist()
        await ctx.send(f"{ticker}가 관심종목에 추가되었습니다.")
        logging.info(f'Ticker {ticker} added to watchlist')
    else:
        await ctx.send(f"{ticker}는 이미 관심종목에 있습니다.")
        logging.info(f'Ticker {ticker} is already in watchlist')


@bot.command(name='관심종목제거')
async def remove_from_watchlist(ctx, ticker: str):
    ticker = ticker.upper()
    logging.info(f'Command !관심종목제거 invoked for ticker: {ticker}')
    if ticker in watchlist:
        watchlist.remove(ticker)
        save_watchlist()
        await ctx.send(f"{ticker}가 관심종목에서 제거되었습니다.")
        logging.info(f'Ticker {ticker} removed from watchlist')
    else:
        await ctx.send(f"{ticker}는 관심종목에 없습니다.")
        logging.warning(f'Ticker {ticker} not found in watchlist')


# 관심종목을 watchlist.txt 파일에 저장하는 함수
def save_watchlist():
    with open(WATCHLIST_FILE, 'w') as f:
        for ticker in watchlist:
            f.write(f"{ticker}\n")
    logging.info('Watchlist saved to file')


# watchlist.txt 파일에서 관심종목을 불러오는 함수
def load_watchlist():
    global watchlist
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'r') as file:
            watchlist = [line.strip().upper() for line in file if line.strip()]
        logging.info('Watchlist loaded from file')
    else:
        watchlist = []
        logging.info('No watchlist file found, starting with empty watchlist')


async def check_watchlist():
    logging.info('Running check_watchlist')
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        logging.error("채널을 찾을 수 없습니다. CHANNEL_ID를 확인하세요.")
        return

    for ticker in watchlist:
        try:
            # 주식 데이터 가져오기 (2년간)
            data = yf.download(ticker, period='2Y')
            latest_close = data['Close'].iloc[-1]
            previous_close = data['Close'].iloc[-2]
            change_percent = ((latest_close - previous_close) / previous_close) * 100

            # 이동평균선 계산
            ma_20 = data['Close'].rolling(window=20).mean().iloc[-1]
            ma_50 = data['Close'].rolling(window=50).mean().iloc[-1]
            ma_100 = data['Close'].rolling(window=100).mean().iloc[-1]
            ma_200 = data['Close'].rolling(window=200).mean().iloc[-1]

            # 종가와 이동평균선 비교
            crossed_mas = []
            if (previous_close > ma_20 and latest_close < ma_20) or (previous_close < ma_20 and latest_close > ma_20):
                crossed_mas.append('20MA')
            if (previous_close > ma_50 and latest_close < ma_50) or (previous_close < ma_50 and latest_close > ma_50):
                crossed_mas.append('50MA')
            if (previous_close > ma_100 and latest_close < ma_100) or (previous_close < ma_100 and latest_close > ma_100):
                crossed_mas.append('100MA')
            if (previous_close > ma_200 and latest_close < ma_200) or (previous_close < ma_200 and latest_close > ma_200):
                crossed_mas.append('200MA')

            # 출력 내용 생성
            message = f"**{ticker}**의 종가: {latest_close:.2f}\n이전 종가 대비 변화율: {change_percent:.2f}%\n"

            if crossed_mas:
                message += f"크로스된 MA: {', '.join(crossed_mas)}\n"

            # 중요한 변화가 있을 때만 차트 전송
            send_chart_flag = False
            if abs(change_percent) >= 5 or crossed_mas:
                send_chart_flag = True

            # 디스코드 채널에 결과 전송
            await channel.send(message)
            data_size = len(message.encode('utf-8'))
            logging.info(f'Sent watchlist message for ticker: {ticker}, size: {data_size} bytes', extra={'data_size': data_size})

            if send_chart_flag:
                # 차트 생성
                plt.figure(figsize=(6, 4), dpi=80)
                plt.plot(data['Close'], label='Close Price')
                plt.plot(data['Close'].rolling(window=20).mean(), label='20MA')
                plt.plot(data['Close'].rolling(window=50).mean(), label='50MA')
                plt.plot(data['Close'].rolling(window=100).mean(), label='100MA')
                plt.plot(data['Close'].rolling(window=200).mean(), label='200MA')
                plt.title(f"{ticker} Chart")
                plt.xlabel("Date")
                plt.ylabel("Price")
                plt.legend()

                # 차트를 메모리 버퍼에 저장
                buf = io.BytesIO()
                plt.savefig(buf, format='png', dpi=80)
                buf.seek(0)
                plt.close()

                # 버퍼의 크기 계산
                buf_size = buf.getbuffer().nbytes

                # 차트 전송
                await channel.send(file=discord.File(fp=buf, filename=f"{ticker}_chart.png"))
                logging.info(f'Sent chart for ticker: {ticker}, size: {buf_size} bytes', extra={'data_size': buf_size})
            else:
                logging.info(f'No significant changes for ticker: {ticker}')
        except Exception as e:
            logging.error(f"Error processing ticker {ticker}: {e}")


@bot.command(name='관심종목')  # 관심종목 조회
async def display_watchlist(ctx):
    logging.info('Command !관심종목 invoked')
    if watchlist:
        message = f"현재 관심종목 리스트: {', '.join(watchlist)}"
        await ctx.send(message)
        data_size = len(message.encode('utf-8'))
        logging.info(f'Sent watchlist to user, size: {data_size} bytes', extra={'data_size': data_size})
    else:
        message = "현재 관심종목에 등록된 종목이 없습니다."
        await ctx.send(message)
        data_size = len(message.encode('utf-8'))
        logging.info(f'Sent empty watchlist message, size: {data_size} bytes', extra={'data_size': data_size})


@bot.command(name='종가')
async def stock_price(ctx, *tickers):
    logging.info(f'Command !종가 invoked with tickers: {tickers}')
    if len(tickers) == 0:
        # 티커가 입력되지 않으면 관심종목 사용
        await stock_price_notification(ctx.channel)
    else:
        # 사용자가 입력한 티커들에 대해 종가 출력
        messages = []
        for ticker in tickers:
            message = await get_single_stock_price_message(ticker)
            messages.append(message)
        combined_message = "\n".join(messages)
        await ctx.send(combined_message)
        data_size = len(combined_message.encode('utf-8'))
        logging.info(f'Sent stock prices for provided tickers, size: {data_size} bytes', extra={'data_size': data_size})


async def stock_price_notification(channel=None):
    logging.info('Running stock_price_notification')
    if channel is None:
        channel = bot.get_channel(CHANNEL_ID)
    if channel is not None:
        messages = []
        for ticker in watchlist:
            message = await get_single_stock_price_message(ticker)
            messages.append(message)
        combined_message = "\n".join(messages)
        await channel.send(combined_message)
        data_size = len(combined_message.encode('utf-8'))
        logging.info(f'Sent stock prices for watchlist, size: {data_size} bytes', extra={'data_size': data_size})
    else:
        logging.error("채널을 찾을 수 없습니다. CHANNEL_ID를 확인하세요.")


async def get_single_stock_price_message(ticker):
    try:
        data = yf.download(ticker, period='5d')
        latest_close = data['Close'].iloc[-1]
        previous_close = data['Close'].iloc[-2]
        change_percent = ((latest_close - previous_close) / previous_close) * 100
        message = f"{datetime.now().strftime('%Y-%m-%d')} **{ticker.upper()}** 종가: ${latest_close:.2f} ({change_percent:.2f}%)"
        logging.info(f'Got stock price for ticker: {ticker}')
        return message
    except Exception as e:
        logging.error(f"Error getting stock price for ticker {ticker}: {e}")
        return f"티커 {ticker}에 대한 정보를 가져오는데 실패했습니다: {e}"


@bot.command(name='RSI')  # 특정 티커의 RSI 출력
async def calculate_rsi(ctx, ticker: str):
    ticker = ticker.upper()
    logging.info(f'Command !RSI invoked for ticker: {ticker}')
    try:
        # 특정 티커의 데이터 가져오기 (6개월)
        data = yf.download(ticker, period='6mo')

        # 종가 데이터
        closing_prices = data['Close']

        # RSI 계산
        delta = closing_prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        # 최신 RSI 값
        latest_rsi = rsi.iloc[-1]

        # 결과 출력
        result = f"{ticker}의 최신 RSI: {latest_rsi:.2f}"
        await ctx.send(result)
        data_size = len(result.encode('utf-8'))
        logging.info(f'Sent RSI for ticker: {ticker}, size: {data_size} bytes', extra={'data_size': data_size})
    except Exception as e:
        error_message = f"RSI를 계산하는 중 오류가 발생했습니다: {e}"
        await ctx.send(error_message)
        data_size = len(error_message.encode('utf-8'))
        logging.error(f"Error calculating RSI for ticker {ticker}: {e}", extra={'data_size': data_size})


@bot.command(name='TQQQ_MA')
async def calculate_ma(ctx):
    logging.info('Command !TQQQ_MA invoked')
    await calculate_ma_scheduled()


async def calculate_ma_scheduled():
    logging.info('Running calculate_ma_scheduled')
    channel = bot.get_channel(CHANNEL_ID)
    if channel is not None:
        await send_TQQQ_MA(channel)
        await send_SOXL_MA(channel)
    else:
        logging.error("채널을 찾을 수 없습니다. CHANNEL_ID를 확인하세요.")


async def send_TQQQ_MA(channel):
    ticker = 'TQQQ'
    logging.info(f'Processing MA for ticker: {ticker}')
    try:
        data = yf.download(ticker, period='250d')  # 약 1년치 데이터

        # 종가 데이터
        closing_prices = data['Close']

        # 이동평균선 계산
        ma_20 = closing_prices.rolling(window=20).mean()
        ma_200 = closing_prices.rolling(window=200).mean()

        # 최신 데이터
        latest_close = closing_prices.iloc[-1]
        previous_close = closing_prices.iloc[-2]
        latest_ma_20 = ma_20.iloc[-1]
        previous_ma_20 = ma_20.iloc[-2]
        latest_ma_200 = ma_200.iloc[-1]
        previous_ma_200 = ma_200.iloc[-2]

        # 변화율 계산
        change_percent = ((latest_close - previous_close) / previous_close) * 100

        # 매수/매도 신호 판별
        significant = False
        signals = []
        if previous_close > previous_ma_20 and latest_close < latest_ma_20:
            signals.append("20MA TQQQ 매도 신호")
            significant = True
        elif previous_close < previous_ma_20 and latest_close > latest_ma_20:
            signals.append("20MA TQQQ 매수 신호")
            significant = True
        if previous_close > previous_ma_200 and latest_close < latest_ma_200:
            signals.append("200MA TQQQ 매도 신호")
            significant = True
        elif previous_close < previous_ma_200 and latest_close > latest_ma_200:
            signals.append("200MA TQQQ 매수 신호")
            significant = True

        if significant:
            result = (f"TQQQ의 이전 종가: {previous_close:.2f}\n"
                      f"TQQQ의 최신 종가: {latest_close:.2f} ({change_percent:.2f}%)\n"
                      f"20일 이동평균선: {latest_ma_20:.2f}\n"
                      f"200일 이동평균선: {latest_ma_200:.2f}\n"
                      f"{', '.join(signals)}")
            await channel.send(result)
            data_size = len(result.encode('utf-8'))
            logging.info(f'Sent MA message for ticker: {ticker}, size: {data_size} bytes', extra={'data_size': data_size})
        else:
            logging.info(f'No significant changes for ticker: {ticker}')
    except Exception as e:
        error_message = f"TQQQ의 MA를 계산하는 중 오류가 발생했습니다: {e}"
        await channel.send(error_message)
        data_size = len(error_message.encode('utf-8'))
        logging.error(f"Error calculating MA for ticker {ticker}: {e}", extra={'data_size': data_size})


async def send_SOXL_MA(channel):
    ticker = 'SOXL'
    logging.info(f'Processing MA for ticker: {ticker}')
    try:
        data = yf.download(ticker, period='250d')  # 약 1년치 데이터

        # 종가 데이터
        closing_prices = data['Close']

        # 이동평균선 계산
        ma_20 = closing_prices.rolling(window=20).mean()
        ma_200 = closing_prices.rolling(window=200).mean()

        # 최신 데이터
        latest_close = closing_prices.iloc[-1]
        previous_close = closing_prices.iloc[-2]
        latest_ma_20 = ma_20.iloc[-1]
        previous_ma_20 = ma_20.iloc[-2]
        latest_ma_200 = ma_200.iloc[-1]
        previous_ma_200 = ma_200.iloc[-2]

        # 변화율 계산
        change_percent = ((latest_close - previous_close) / previous_close) * 100

        # 매수/매도 신호 판별
        significant = False
        signals = []
        if previous_close > previous_ma_20 and latest_close < latest_ma_20:
            signals.append("20MA SOXL 매도 신호")
            significant = True
        elif previous_close < previous_ma_20 and latest_close > latest_ma_20:
            signals.append("20MA SOXL 매수 신호")
            significant = True
        if previous_close > previous_ma_200 and latest_close < latest_ma_200:
            signals.append("200MA SOXL 매도 신호")
            significant = True
        elif previous_close < previous_ma_200 and latest_close > latest_ma_200:
            signals.append("200MA SOXL 매수 신호")
            significant = True

        if significant:
            result = (f"SOXL의 이전 종가: {previous_close:.2f}\n"
                      f"SOXL의 최신 종가: {latest_close:.2f} ({change_percent:.2f}%)\n"
                      f"20일 이동평균선: {latest_ma_20:.2f}\n"
                      f"200일 이동평균선: {latest_ma_200:.2f}\n"
                      f"{', '.join(signals)}")
            await channel.send(result)
            data_size = len(result.encode('utf-8'))
            logging.info(f'Sent MA message for ticker: {ticker}, size: {data_size} bytes', extra={'data_size': data_size})
        else:
            logging.info(f'No significant changes for ticker: {ticker}')
    except Exception as e:
        error_message = f"SOXL의 MA를 계산하는 중 오류가 발생했습니다: {e}"
        await channel.send(error_message)
        data_size = len(error_message.encode('utf-8'))
        logging.error(f"Error calculating MA for ticker {ticker}: {e}", extra={'data_size': data_size})


# 봇 실행
bot.run(TOKEN)
