import discord
import yfinance as yf
import pandas as pd
import os
import matplotlib.pyplot as plt
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# 디스코드 봇 토큰
TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = 1272735912148861011  # 메세지를 보낼 디스코드 채널 ID를 입력하세요

if TOKEN is None:
    raise ValueError("DISCORD_TOKEN is not set. Check your .env file.")

# 조회할 주식 티커 리스트
STOCK_TICKERS = ['SPY', 'QQQ']  # 원하는 주식 티커를 추가하세요

# 인텐트 설정
intents = discord.Intents.default()
intents.message_content = True  # 메시지 내용 인텐트 활성화# 메시지 내용에 접근할 수 있도록 설정

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
    print(f'Logged in as {bot.user}')
    
    load_watchlist()
    
    # 매일 오전 5시 30분에 stock_price_notification 함수를 실행하도록 스케줄러 설정
    scheduler.add_job(calculate_ma_scheduled, 'cron', day_of_week='sun-thu', hour=20, minute=15)
    scheduler.add_job(stock_price_notification, 'cron', day_of_week='sun-thu', hour=20, minute=16)
    scheduler.add_job(check_watchlist, 'cron', day_of_week='sun-thu', hour=20, minute=17)
    scheduler.add_job(check_news, 'cron', day_of_week='sun-thu', hour=20, minute=18)
    scheduler.start()

# 관심종목 관련 뉴스 출력
async def check_news():
    """관심종목에 대해 최신 뉴스를 체크하여 디스코드로 전송"""
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
                messages.append(f"{ticker}: {headline}\n링크: {link}")
    
    if messages:
        channel = bot.get_channel(CHANNEL_ID)
        if channel:
            await channel.send("\n\n".join(messages))
        else:
            print("채널을 찾을 수 없습니다.")

# MA 계산 함수
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
    
    # 주식 데이터 가져오기 (1년간)
    data = yf.download(ticker, period='1y')
    
    if data.empty:
        await ctx.send(f"{ticker}에 대한 데이터를 가져올 수 없습니다.")
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
        await channel.send(message)

@bot.command(name='관심종목추가')
async def add_to_watchlist(ctx, ticker: str):
    ticker = ticker.upper()
    if ticker not in watchlist:
        watchlist.append(ticker)
        save_watchlist()
        await ctx.send(f"{ticker}가 관심종목에 추가되었습니다.")
    else:
        await ctx.send(f"{ticker}는 이미 관심종목에 있습니다.")

@bot.command(name='관심종목제거')
async def remove_from_watchlist(ctx, ticker: str):
    ticker = ticker.upper()
    if ticker in watchlist:
        watchlist.remove(ticker)
        save_watchlist()  # 관심종목이 제거될 때마다 파일에 저장
        await ctx.send(f"{ticker}가 관심종목에서 제거되었습니다.")
    else:
        await ctx.send(f"{ticker}는 관심종목에 없습니다.")

"""관심종목을 watchlist.txt 파일에 저장하는 함수"""
def save_watchlist():
    with open(WATCHLIST_FILE, 'w') as f:
        for ticker in watchlist:
            f.write(f"{ticker}\n")

"""watchlist.txt 파일에서 관심종목을 불러오는 함수"""
def load_watchlist():
    global watchlist
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'r') as file:
            watchlist = [line.strip().upper() for line in file if line.strip()]
    else:
        watchlist = []

async def check_watchlist():
    for ticker in watchlist:
        # 주식 데이터 가져오기 (1년간)
        data = yf.download(ticker, period='2Y')
        latest_close = data['Close'].iloc[-1]
        previous_close = data['Close'].iloc[-2]
        change_percent = ((latest_close - previous_close) / previous_close) * 100

        # 이동평균선 계산 (20, 50, 100, 200일)
        ma_20 = data['Close'].rolling(window=20).mean().iloc[-1]
        ma_50 = data['Close'].rolling(window=50).mean().iloc[-1]
        ma_100 = data['Close'].rolling(window=100).mean().iloc[-1]
        ma_200 = data['Close'].rolling(window=200).mean().iloc[-1]

        # 종가와 이동평균선 비교
        crossed_mas = []
        if previous_close > ma_20 and latest_close < ma_20 or previous_close < ma_20 and latest_close > ma_20:
            crossed_mas.append('20MA')
        if previous_close > ma_50 and latest_close < ma_50 or previous_close < ma_50 and latest_close > ma_50:
            crossed_mas.append('50MA')
        if previous_close > ma_100 and latest_close < ma_100 or previous_close < ma_100 and latest_close > ma_100:
            crossed_mas.append('100MA')
        if previous_close > ma_200 and latest_close < ma_200 or previous_close < ma_200 and latest_close > ma_200:
            crossed_mas.append('200MA')

        # 출력 내용 생성
        message = f"{ticker}의 종가: {latest_close:.2f}\n이전 종가 대비 변화율: {change_percent:.2f}%\n"

        if crossed_mas:
            message += f"크로스된 MA: {', '.join(crossed_mas)}\n"

        # 차트 생성
        plt.figure(figsize=(10, 6))
        plt.plot(data['Close'], label='Close Price')
        plt.plot(data['Close'].rolling(window=20).mean(), label='20MA')
        plt.plot(data['Close'].rolling(window=50).mean(), label='50MA')
        plt.plot(data['Close'].rolling(window=100).mean(), label='100MA')
        plt.plot(data['Close'].rolling(window=200).mean(), label='200MA')
        plt.title(f"{ticker} Chart")
        plt.xlabel("Date")
        plt.ylabel("Price")
        plt.legend()

        # 차트 저장
        chart_file = f"{ticker}_chart.png"
        plt.savefig(chart_file)
        plt.close()

        # 디스코드 채널에 결과 전송
        channel = bot.get_channel(CHANNEL_ID)  # CHANNEL_ID는 출력할 디스코드 채널의 ID로 설정해야 합니다.
        if channel:
            await channel.send(message)
            await channel.send(file=discord.File(chart_file))

@bot.command(name='관심종목') #관심종목 조회
async def display_watchlist(ctx):
    if watchlist:
        await ctx.send(f"현재 관심종목 리스트: {', '.join(watchlist)}")
    else:
        await ctx.send("현재 관심종목에 등록된 종목이 없습니다.")

@bot.command(name='종가')
async def stock_price(ctx, *tickers):
    if len(tickers) == 0:
        # 티커가 입력되지 않으면 기본 티커 리스트를 사용
        await stock_price_notification(ctx.channel)
    else:
        # 사용자가 입력한 티커들에 대해 종가 출력
        for ticker in tickers:
            await send_single_stock_price(ctx.channel, ticker)

async def stock_price_notification(channel=None): #종가 출력 함수
    try:
        # 채널이 지정되지 않은 경우 기본 채널 사용
        if channel is None:
            channel = bot.get_channel(CHANNEL_ID)
        
        if channel is not None:
            # 관심종목에 대해 종가를 가져와서 메시지로 전송
            for ticker in watchlist:
                await send_single_stock_price(channel, ticker)
        else:
            print("채널을 찾을 수 없습니다. CHANNEL_ID를 확인하세요.")
    except Exception as e:
        print(f"주식 정보를 가져오는데 실패했습니다: {e}")
        if channel is not None:
            await channel.send(f"주식 정보를 가져오는데 실패했습니다: {e}")

async def send_single_stock_price(channel, ticker): #개별 종가 출력 함수
    try:
        # 2일간의 데이터를 가져옵니다.
        data = yf.download(ticker, period='5d')
    
        # 최신 종가와 이전 종가를 가져옵니다.
        latest_close = data['Close'].iloc[-1]
        previous_close = data['Close'].iloc[-2]
        
        # 변화율을 계산합니다.
        change_percent = ((latest_close - previous_close) / previous_close) * 100
        
        await channel.send(f"{datetime.now().strftime('%Y-%m-%d')} {ticker} 종가: ${latest_close:.2f} ({change_percent:.2f}%)")
    except Exception as e:
        await channel.send(f"티커 {ticker}에 대한 정보를 가져오는데 실패했습니다: {e}")

@bot.command(name='RSI')#특정 티커의 RSI 출력
async def calculate_rsi(ctx, ticker: str):
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
        result = f"{ticker.upper()}의 최신 RSI: {latest_rsi:.2f}"
        await ctx.send(result)
    except Exception as e:
        await ctx.send(f"RSI를 계산하는 중 오류가 발생했습니다: {e}")

@bot.command(name='TQQQ_MA')
async def calculate_ma(ctx):
    await send_TQQQ_MA(ctx.channel)

async def calculate_ma_scheduled():
    channel = bot.get_channel(CHANNEL_ID)
    if channel is not None:
        await send_TQQQ_MA(channel)
        await send_SOXL_MA(channel)
    else:
        print("채널을 찾을 수 없습니다. CHANNEL_ID를 확인하세요.")

async def send_TQQQ_MA(ctx):#TQQQ의 20MA, 200MA를 출력
    try:
        # TQQQ의 지난 1년간의 데이터 가져오기
        ticker = 'TQQQ'
        data = yf.download(ticker, period='2y')

        # 종가 데이터
        closing_prices = data['Close']

        # 20일 이동편균선 계산
        ma_20 = closing_prices.rolling(window=20).mean()
        
        # 200일 이동평균선 계산
        ma_200 = closing_prices.rolling(window=200).mean()

        # 20일 이동평균선 + 10% 계산
        ma_20_plus_10 = ma_20 * 1.10

        # 200일 이동평균선 + 10% 계산
        ma_200_plus_10 = ma_200 * 1.10

        # 최신 데이터
        latest_close = closing_prices.iloc[-1]
        latest_ma_200 = ma_200.iloc[-1]
        latest_ma_200_plus_10 = ma_200_plus_10.iloc[-1]
        latest_ma_20 = ma_20.iloc[-1]
        latest_ma_20_plus_10 = ma_20_plus_10.iloc[-1]

        # 이전 종가와 200MA 계산
        previous_close = closing_prices.iloc[-2]
        previous_ma_200 = ma_200.iloc[-2]
        previous_ma_20 = ma_20.iloc[-2]

        # 변화율 계산
        change_percent = ((latest_close - previous_close) / previous_close) * 100

        # 결과 생성
        result = (f"TQQQ의 이전 종가: {previous_close:.2f}\n"
              f"TQQQ의 최신 종가: {latest_close:.2f} ({change_percent:.2f}%)\n"
              f"20일 이동평균선: {latest_ma_20:.2f}\n"
              f"20일 이동평균선 + 10%: {latest_ma_20_plus_10:.2f}\n"
              f"200일 이동평균선: {latest_ma_200:.2f}\n"
              f"200일 이동평균선 + 10%: {latest_ma_200_plus_10:.2f}\n")

        # 매도/매수 판별
        if previous_close > previous_ma_20 and latest_close < latest_ma_20:
            result += "20MA TQQQ 매도"  # 위에서 아래로 내려간 경우
        elif previous_close < previous_ma_20 and latest_close > latest_ma_20:
            result += "20MA TQQQ 매수"  # 아래에서 위로 올라간 경우
        elif previous_close > previous_ma_200 and latest_close < latest_ma_200:
            result += "200MA TQQQ 매도"  # 위에서 아래로 내려간 경우
        elif previous_close < previous_ma_200 and latest_close > latest_ma_200:
            result += "200MA TQQQ 매수"  # 아래에서 위로 올라간 경우
        else:
            result += "TQQQ의 종가는 큰 변화가 없습니다."

        # 채널에 결과 전송
            await ctx.send(result)
    except Exception as e:
        await ctx.send(f"TQQQ의 MA를 계산하는 중 오류가 발생했습니다: {e}")

async def send_SOXL_MA(ctx):#SOXL의 20MA, 200MA를 출력
    try:
        # TQQQ의 지난 1년간의 데이터 가져오기
        ticker = 'SOXL'
        data = yf.download(ticker, period='2y')

        # 종가 데이터
        closing_prices = data['Close']

        # 20일 이동편균선 계산
        ma_20 = closing_prices.rolling(window=20).mean()
        
        # 200일 이동평균선 계산
        ma_200 = closing_prices.rolling(window=200).mean()

        # 20일 이동평균선 + 10% 계산
        ma_20_plus_10 = ma_20 * 1.10

        # 200일 이동평균선 + 10% 계산
        ma_200_plus_10 = ma_200 * 1.10

        # 최신 데이터
        latest_close = closing_prices.iloc[-1]
        latest_ma_200 = ma_200.iloc[-1]
        latest_ma_200_plus_10 = ma_200_plus_10.iloc[-1]
        latest_ma_20 = ma_20.iloc[-1]
        latest_ma_20_plus_10 = ma_20_plus_10.iloc[-1]

        # 이전 종가와 200MA 계산
        previous_close = closing_prices.iloc[-2]
        previous_ma_200 = ma_200.iloc[-2]
        previous_ma_20 = ma_20.iloc[-2]

        # 변화율 계산
        change_percent = ((latest_close - previous_close) / previous_close) * 100

        # 결과 생성
        result = (f"SOXL의 이전 종가: {previous_close:.2f}\n"
              f"SOXL의 최신 종가: {latest_close:.2f} ({change_percent:.2f}%)\n"
              f"20일 이동평균선: {latest_ma_20:.2f}\n"
              f"20일 이동평균선 + 10%: {latest_ma_20_plus_10:.2f}\n"
              f"200일 이동평균선: {latest_ma_200:.2f}\n"
              f"200일 이동평균선 + 10%: {latest_ma_200_plus_10:.2f}\n")

        # 매도/매수 판별
        if previous_close > previous_ma_20 and latest_close < latest_ma_20:
            result += "20MA SOXL 매도"  # 위에서 아래로 내려간 경우
        elif previous_close < previous_ma_20 and latest_close > latest_ma_20:
            result += "20MA SOXL 매수"  # 아래에서 위로 올라간 경우
        elif previous_close > previous_ma_200 and latest_close < latest_ma_200:
            result += "200MA SOXL 매도"  # 위에서 아래로 내려간 경우
        elif previous_close < previous_ma_200 and latest_close > latest_ma_200:
            result += "200MA SOXL 매수"  # 아래에서 위로 올라간 경우
        else:
            result += "SOXL의 종가는 큰 변화가 없습니다."

        # 채널에 결과 전송
            await ctx.send(result)
    except Exception as e:
        await ctx.send(f"SOXL의 MA를 계산하는 중 오류가 발생했습니다: {e}")

# 봇 실행
bot.run(TOKEN)