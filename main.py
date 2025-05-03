import os
import time
import requests
import threading
from flask import Flask
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv('API_KEY')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

THEODDSAPI_URL = 'https://api.the-odds-api.com/v4/sports/basketball_nba/odds/'
BOOKMAKERS = ['fanduel', 'draftkings']
REGION = 'us'
MARKETS = 'h2h'

app = Flask(__name__)

def get_odds():
    params = {
        'apiKey': API_KEY,
        'regions': REGION,
        'markets': MARKETS,
        'bookmakers': ','.join(BOOKMAKERS),
        'oddsFormat': 'american',
    }
    response = requests.get(THEODDSAPI_URL, params=params)
    response.raise_for_status()
    return response.json()

def implied_prob(odds):
    if odds > 0:
        return 100 / (odds + 100)
    else:
        return abs(odds) / (abs(odds) + 100)

def find_arbitrage(games):
    arbs = []
    for game in games:
        teams = game['teams']
        odds_dict = {team: {} for team in teams}
        for bookmaker in game['bookmakers']:
            if bookmaker['key'] in BOOKMAKERS:
                for outcome in bookmaker['markets'][0]['outcomes']:
                    odds_dict[outcome['name']][bookmaker['key']] = outcome['price']
        # Only consider if both books have both teams
        if all(len(odds_dict[team]) == 2 for team in teams):
            odds1 = odds_dict[teams[0]]
            odds2 = odds_dict[teams[1]]
            # Try both combinations
            for t1, t2 in [(teams[0], teams[1]), (teams[1], teams[0])]:
                o1 = odds_dict[t1]['fanduel']
                o2 = odds_dict[t2]['draftkings']
                if o1 > 0 and o2 > 0:
                    prob = implied_prob(o1) + implied_prob(o2)
                    if prob < 1:
                        arbs.append({
                            'game': game['home_team'] + ' vs ' + game['away_team'],
                            'team1': t1,
                            'team2': t2,
                            'fanduel_odds': o1,
                            'draftkings_odds': o2,
                            'implied_prob': prob
                        })
    return arbs

def send_telegram_alert(message):
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    data = {'chat_id': CHAT_ID, 'text': message}
    requests.post(url, data=data)

def check_and_alert():
    try:
        games = get_odds()
        arbs = find_arbitrage(games)
        for arb in arbs:
            msg = (f"Arbitrage Opportunity!\n"
                   f"Game: {arb['game']}\n"
                   f"{arb['team1']} (FanDuel): {arb['fanduel_odds']}\n"
                   f"{arb['team2']} (DraftKings): {arb['draftkings_odds']}\n"
                   f"Implied Probability: {arb['implied_prob']*100:.2f}%")
            send_telegram_alert(msg)
    except Exception as e:
        print(f"Error: {e}")

def periodic_check():
    while True:
        check_and_alert()
        time.sleep(300)  # 5 minutes

def start_periodic_thread():
    t = threading.Thread(target=periodic_check, daemon=True)
    t.start()

@app.route('/')
def home():
    return 'NBA Arbitrage Bot is running!'

if __name__ == '__main__':
    start_periodic_thread()
    app.run(host='0.0.0.0', port=8080) 