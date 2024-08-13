import discord
import yfinance as yf
import pandas as pd
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
import os
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

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    
    # 매일 오전 5시 30분에 stock_price_notification 함수를 실행하도록 스케줄러 설정
    scheduler.add_job(stock_price_notification, 'cron', hour=20, minute=30)
    scheduler.add_job(calculate_ma_scheduled, 'cron', hour=20, minute=15)
    scheduler.start()

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
            # 각 주식 티커에 대해 종가를 가져와서 메시지로 전송
            for ticker in STOCK_TICKERS:
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

@bot.command(name='TQQQ_MA')
async def calculate_ma(ctx):
    await send_TQQQ_MA(ctx.channel)

async def calculate_ma_scheduled():
    channel = bot.get_channel(CHANNEL_ID)
    if channel is not None:
        await send_TQQQ_MA(channel)
    else:
        print("채널을 찾을 수 없습니다. CHANNEL_ID를 확인하세요.")

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

async def send_TQQQ_MA(ctx):#TQQQ의 20MA, 200MA를 출력
    try:
        # TQQQ의 지난 1년간의 데이터 가져오기
        ticker = 'TQQQ'
        data = yf.download(ticker, period='1y')

        # 종가 데이터
        closing_prices = data['Close']

        # 200일 이동평균선 계산
        ma_200 = closing_prices.rolling(window=200).mean()

        # 20일 이동편균선 계산
        ma_20 = closing_prices.rolling(window=20).mean()

        # 200일 이동평균선 + 10% 계산
        ma_200_plus_10 = ma_200 * 1.10
    
        # 20일 이동평균선 + 10% 계산
        ma_20_plus_10 = ma_20 * 1.10

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
        result = (f"TQQQ의 이전 종가: {previous_close:.2f} ({change_percent:.2f}%)\n"
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
        if previous_close > previous_ma_200 and latest_close < latest_ma_200:
            result += "200MA TQQQ 매도"  # 위에서 아래로 내려간 경우
        elif previous_close < previous_ma_200 and latest_close > latest_ma_200:
            result += "200MA TQQQ 매수"  # 아래에서 위로 올라간 경우
        else:
            result += "TQQQ의 종가는 큰 변화가 없습니다."

        # 채널에 결과 전송
            await ctx.send(result)
    except Exception as e:
        await ctx.send(f"RSI를 계산하는 중 오류가 발생했습니다: {e}")
    
# 봇 실행
bot.run(TOKEN)