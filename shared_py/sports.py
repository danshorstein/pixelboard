"""Sport rotation policy. Missing settings retain the existing device behavior."""
from copy import deepcopy

TEAM_CATALOG = {'nba': [{'abbr': 'ATL', 'name': 'Atlanta Hawks'},
         {'abbr': 'BOS', 'name': 'Boston Celtics'},
         {'abbr': 'BKN', 'name': 'Brooklyn Nets'},
         {'abbr': 'CHA', 'name': 'Charlotte Hornets'},
         {'abbr': 'CHI', 'name': 'Chicago Bulls'},
         {'abbr': 'CLE', 'name': 'Cleveland Cavaliers'},
         {'abbr': 'DAL', 'name': 'Dallas Mavericks'},
         {'abbr': 'DEN', 'name': 'Denver Nuggets'},
         {'abbr': 'DET', 'name': 'Detroit Pistons'},
         {'abbr': 'GS', 'name': 'Golden State Warriors'},
         {'abbr': 'HOU', 'name': 'Houston Rockets'},
         {'abbr': 'IND', 'name': 'Indiana Pacers'},
         {'abbr': 'LAC', 'name': 'LA Clippers'},
         {'abbr': 'LAL', 'name': 'Los Angeles Lakers'},
         {'abbr': 'MEM', 'name': 'Memphis Grizzlies'},
         {'abbr': 'MIA', 'name': 'Miami Heat'},
         {'abbr': 'MIL', 'name': 'Milwaukee Bucks'},
         {'abbr': 'MIN', 'name': 'Minnesota Timberwolves'},
         {'abbr': 'NO', 'name': 'New Orleans Pelicans'},
         {'abbr': 'NY', 'name': 'New York Knicks'},
         {'abbr': 'OKC', 'name': 'Oklahoma City Thunder'},
         {'abbr': 'ORL', 'name': 'Orlando Magic'},
         {'abbr': 'PHI', 'name': 'Philadelphia 76ers'},
         {'abbr': 'PHX', 'name': 'Phoenix Suns'},
         {'abbr': 'POR', 'name': 'Portland Trail Blazers'},
         {'abbr': 'SAC', 'name': 'Sacramento Kings'},
         {'abbr': 'SA', 'name': 'San Antonio Spurs'},
         {'abbr': 'TOR', 'name': 'Toronto Raptors'},
         {'abbr': 'UTAH', 'name': 'Utah Jazz'},
         {'abbr': 'WSH', 'name': 'Washington Wizards'}],
 'nhl': [{'abbr': 'ANA', 'name': 'Anaheim Ducks'},
         {'abbr': 'BOS', 'name': 'Boston Bruins'},
         {'abbr': 'BUF', 'name': 'Buffalo Sabres'},
         {'abbr': 'CGY', 'name': 'Calgary Flames'},
         {'abbr': 'CAR', 'name': 'Carolina Hurricanes'},
         {'abbr': 'CHI', 'name': 'Chicago Blackhawks'},
         {'abbr': 'COL', 'name': 'Colorado Avalanche'},
         {'abbr': 'CBJ', 'name': 'Columbus Blue Jackets'},
         {'abbr': 'DAL', 'name': 'Dallas Stars'},
         {'abbr': 'DET', 'name': 'Detroit Red Wings'},
         {'abbr': 'EDM', 'name': 'Edmonton Oilers'},
         {'abbr': 'FLA', 'name': 'Florida Panthers'},
         {'abbr': 'LA', 'name': 'Los Angeles Kings'},
         {'abbr': 'MIN', 'name': 'Minnesota Wild'},
         {'abbr': 'MTL', 'name': 'Montreal Canadiens'},
         {'abbr': 'NSH', 'name': 'Nashville Predators'},
         {'abbr': 'NJ', 'name': 'New Jersey Devils'},
         {'abbr': 'NYI', 'name': 'New York Islanders'},
         {'abbr': 'NYR', 'name': 'New York Rangers'},
         {'abbr': 'OTT', 'name': 'Ottawa Senators'},
         {'abbr': 'PHI', 'name': 'Philadelphia Flyers'},
         {'abbr': 'PIT', 'name': 'Pittsburgh Penguins'},
         {'abbr': 'SJ', 'name': 'San Jose Sharks'},
         {'abbr': 'SEA', 'name': 'Seattle Kraken'},
         {'abbr': 'STL', 'name': 'St. Louis Blues'},
         {'abbr': 'TB', 'name': 'Tampa Bay Lightning'},
         {'abbr': 'TOR', 'name': 'Toronto Maple Leafs'},
         {'abbr': 'UTAH', 'name': 'Utah Mammoth'},
         {'abbr': 'VAN', 'name': 'Vancouver Canucks'},
         {'abbr': 'VGK', 'name': 'Vegas Golden Knights'},
         {'abbr': 'WSH', 'name': 'Washington Capitals'},
         {'abbr': 'WPG', 'name': 'Winnipeg Jets'}],
 'nfl': [{'abbr': 'ARI', 'name': 'Arizona Cardinals'},
         {'abbr': 'ATL', 'name': 'Atlanta Falcons'},
         {'abbr': 'BAL', 'name': 'Baltimore Ravens'},
         {'abbr': 'BUF', 'name': 'Buffalo Bills'},
         {'abbr': 'CAR', 'name': 'Carolina Panthers'},
         {'abbr': 'CHI', 'name': 'Chicago Bears'},
         {'abbr': 'CIN', 'name': 'Cincinnati Bengals'},
         {'abbr': 'CLE', 'name': 'Cleveland Browns'},
         {'abbr': 'DAL', 'name': 'Dallas Cowboys'},
         {'abbr': 'DEN', 'name': 'Denver Broncos'},
         {'abbr': 'DET', 'name': 'Detroit Lions'},
         {'abbr': 'GB', 'name': 'Green Bay Packers'},
         {'abbr': 'HOU', 'name': 'Houston Texans'},
         {'abbr': 'IND', 'name': 'Indianapolis Colts'},
         {'abbr': 'JAX', 'name': 'Jacksonville Jaguars'},
         {'abbr': 'KC', 'name': 'Kansas City Chiefs'},
         {'abbr': 'LV', 'name': 'Las Vegas Raiders'},
         {'abbr': 'LAC', 'name': 'Los Angeles Chargers'},
         {'abbr': 'LAR', 'name': 'Los Angeles Rams'},
         {'abbr': 'MIA', 'name': 'Miami Dolphins'},
         {'abbr': 'MIN', 'name': 'Minnesota Vikings'},
         {'abbr': 'NE', 'name': 'New England Patriots'},
         {'abbr': 'NO', 'name': 'New Orleans Saints'},
         {'abbr': 'NYG', 'name': 'New York Giants'},
         {'abbr': 'NYJ', 'name': 'New York Jets'},
         {'abbr': 'PHI', 'name': 'Philadelphia Eagles'},
         {'abbr': 'PIT', 'name': 'Pittsburgh Steelers'},
         {'abbr': 'SF', 'name': 'San Francisco 49ers'},
         {'abbr': 'SEA', 'name': 'Seattle Seahawks'},
         {'abbr': 'TB', 'name': 'Tampa Bay Buccaneers'},
         {'abbr': 'TEN', 'name': 'Tennessee Titans'},
         {'abbr': 'WSH', 'name': 'Washington Commanders'}],
 'mlb': [{'abbr': 'AZ', 'name': 'Arizona Diamondbacks'},
         {'abbr': 'ATH', 'name': 'Athletics'},
         {'abbr': 'ATL', 'name': 'Atlanta Braves'},
         {'abbr': 'BAL', 'name': 'Baltimore Orioles'},
         {'abbr': 'BOS', 'name': 'Boston Red Sox'},
         {'abbr': 'CHC', 'name': 'Chicago Cubs'},
         {'abbr': 'CWS', 'name': 'Chicago White Sox'},
         {'abbr': 'CIN', 'name': 'Cincinnati Reds'},
         {'abbr': 'CLE', 'name': 'Cleveland Guardians'},
         {'abbr': 'COL', 'name': 'Colorado Rockies'},
         {'abbr': 'DET', 'name': 'Detroit Tigers'},
         {'abbr': 'HOU', 'name': 'Houston Astros'},
         {'abbr': 'KC', 'name': 'Kansas City Royals'},
         {'abbr': 'LAA', 'name': 'Los Angeles Angels'},
         {'abbr': 'LAD', 'name': 'Los Angeles Dodgers'},
         {'abbr': 'MIA', 'name': 'Miami Marlins'},
         {'abbr': 'MIL', 'name': 'Milwaukee Brewers'},
         {'abbr': 'MIN', 'name': 'Minnesota Twins'},
         {'abbr': 'NYM', 'name': 'New York Mets'},
         {'abbr': 'NYY', 'name': 'New York Yankees'},
         {'abbr': 'PHI', 'name': 'Philadelphia Phillies'},
         {'abbr': 'PIT', 'name': 'Pittsburgh Pirates'},
         {'abbr': 'SD', 'name': 'San Diego Padres'},
         {'abbr': 'SF', 'name': 'San Francisco Giants'},
         {'abbr': 'SEA', 'name': 'Seattle Mariners'},
         {'abbr': 'STL', 'name': 'St. Louis Cardinals'},
         {'abbr': 'TB', 'name': 'Tampa Bay Rays'},
         {'abbr': 'TEX', 'name': 'Texas Rangers'},
         {'abbr': 'TOR', 'name': 'Toronto Blue Jays'},
         {'abbr': 'WSH', 'name': 'Washington Nationals'}]}
LEAGUES = ('mlb', 'nfl', 'nba', 'nhl', 'team')

def validate_sports(value):
    if not isinstance(value, dict) or set(value) - set(LEAGUES):
        raise ValueError('Unknown sports settings')
    result = {}
    for league, entry in value.items():
        if not isinstance(entry, dict) or set(entry) != {'enabled', 'teams'} or type(entry['enabled']) is not bool:
            raise ValueError('Each sport needs enabled and teams')
        teams = entry['teams']
        if league == 'team' and teams is not None: raise ValueError('Team calendar has no league-team filter')
        valid = {t['abbr'] for t in TEAM_CATALOG.get(league, [])}
        if teams is not None and (not isinstance(teams, list) or len(teams) > len(valid)
                or any(not isinstance(t, str) or t not in valid for t in teams)
                or len(teams) != len(set(teams))):
            raise ValueError('Invalid selected teams for ' + league.upper())
        result[league] = deepcopy(entry)
    return result

def sports_settings(project):
    result = {k: {'enabled': k in ('mlb', 'team'), 'teams': None} for k in LEAGUES}
    legacy_nfl = project.get('nfl', {})
    result['nfl']['enabled'] = bool(legacy_nfl.get('enabled', False))
    if legacy_nfl.get('favoritesOnly'): result['nfl']['teams'] = list(legacy_nfl.get('favorites', []))
    result.update(validate_sports(project.get('sports', {})))
    return result

def allows(settings, league, game):
    policy = settings[league]
    return policy['enabled'] and (policy['teams'] is None or
        any(game.get(side, {}).get('abbr') in policy['teams'] for side in ('away', 'home')))

def filter_games(settings, league, games):
    return [g for g in games if allows(settings, league, g)]
