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

SPORTS = ['basketball_nba', 'mma_mixed_martial_arts', 'tennis', 'baseball_mlb', 'americanfootball_nfl']
BOOKMAKERS = ['fanduel', 'draftkings']
REGION = 'us'
MARKETS = ['h2h', 'spreads', 'totals']  # List of all markets to check
TOTAL_STAKE = 100  # Default total stake in dollars
MIN_PROFIT = 3     # Minimum profit in dollars to send alert

app = Flask(__name__)

def get_odds(sport, market):
    params = {
        'apiKey': API_KEY,
        'regions': REGION,
        'markets': market,
        'bookmakers': ','.join(BOOKMAKERS),
        'oddsFormat': 'american',
    }
    url = f'https://api.the-odds-api.com/v4/sports/{sport}/odds/'
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()

def implied_prob(odds):
    if odds > 0:
        return 100 / (odds + 100)
    else:
        return abs(odds) / (abs(odds) + 100)

def calculate_stakes_and_profit(odds1, odds2, total_stake):
    """Calculate optimal stakes and guaranteed profit for an arbitrage opportunity."""
    # Calculate implied probabilities
    p1 = implied_prob(odds1)
    p2 = implied_prob(odds2)
    
    # Calculate stake for each outcome
    stake1 = (total_stake * p1) / (p1 + p2)
    stake2 = total_stake - stake1
    
    # Round stakes to nearest dollar
    stake1 = round(stake1)
    stake2 = round(stake2)
    
    # Calculate potential winnings for each outcome
    if odds1 > 0:
        winnings1 = stake1 * (odds1 / 100 + 1)
    else:
        winnings1 = stake1 * (100 / abs(odds1) + 1)
        
    if odds2 > 0:
        winnings2 = stake2 * (odds2 / 100 + 1)
    else:
        winnings2 = stake2 * (100 / abs(odds2) + 1)
    
    # Calculate guaranteed profit and round to 2 decimal places
    profit = round(min(winnings1, winnings2) - total_stake, 2)
    
    return {
        'stake1': stake1,
        'stake2': stake2,
        'profit': profit
    }

def find_arbitrage(games, sport_title, market):
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
                        # Calculate stakes and profit
                        stakes = calculate_stakes_and_profit(o1, o2, TOTAL_STAKE)
                        if stakes['profit'] >= MIN_PROFIT:
                            arbs.append({
                                'sport': sport_title,
                                'game': game['home_team'] + ' vs ' + game['away_team'],
                                'team1': t1,
                                'team2': t2,
                                'fanduel_odds': o1,
                                'draftkings_odds': o2,
                                'implied_prob': prob,
                                'stake1': stakes['stake1'],
                                'stake2': stakes['stake2'],
                                'profit': stakes['profit'],
                                'market': market
                            })
    return arbs

def send_telegram_alert(message):
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    data = {'chat_id': CHAT_ID, 'text': message}
    requests.post(url, data=data)

def check_and_alert():
    try:
        all_arbs = []
        for sport in SPORTS:
            sport_title = sport.replace('_', ' ').title()
            for market in MARKETS:
                games = get_odds(sport, market)
                arbs = find_arbitrage(games, sport_title, market)
                all_arbs.extend(arbs)
        
        for arb in all_arbs:
            market_display = {
                'h2h': 'Moneyline',
                'spreads': 'Spread',
                'totals': 'Total'
            }.get(arb['market'], arb['market'].upper())
            
            msg = (f"Arbitrage Opportunity!\n"
                   f"Sport: {arb['sport']}\n"
                   f"Market: {market_display}\n"
                   f"Game: {arb['game']}\n"
                   f"Bet ${arb['stake1']} on {arb['team1']} (FanDuel): {arb['fanduel_odds']}\n"
                   f"Bet ${arb['stake2']} on {arb['team2']} (DraftKings): {arb['draftkings_odds']}\n"
                   f"Total Stake: ${TOTAL_STAKE}\n"
                   f"Profit: ${arb['profit']:.2f}\n"
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
    return 'Multi-Sport Arbitrage Bot is running!'

if __name__ == '__main__':
    start_periodic_thread()
    app.run(host='0.0.0.0', port=8080) 
