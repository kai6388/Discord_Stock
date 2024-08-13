import discord
import yfinance as yf
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
STOCK_TICKERS = ['TQQQ', 'NVDA', 'NVDL']  # 원하는 주식 티커를 추가하세요

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
    scheduler.add_job(stock_price_notification, 'cron', hour=5, minute=30)
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

async def stock_price_notification(channel=None):
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

async def send_single_stock_price(channel, ticker):
    try:
        stock = yf.Ticker(ticker)
        closing_price = stock.history(period='1d')['Close'].iloc[0]
        await channel.send(f"{datetime.now().strftime('%Y-%m-%d')} {ticker} 종가: ${closing_price:.2f}")
    except Exception as e:
        await channel.send(f"티커 {ticker}에 대한 정보를 가져오는데 실패했습니다: {e}")

# 봇 실행
bot.run(TOKEN)