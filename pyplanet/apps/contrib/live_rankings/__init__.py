from pyplanet.apps.config import AppConfig
from pyplanet.apps.contrib.live_rankings.views import LiveRankingsWidget

from pyplanet.apps.core.trackmania import callbacks as tm_signals
from pyplanet.apps.core.maniaplanet import callbacks as mp_signals


class LiveRankings(AppConfig):
	game_dependencies = ['trackmania']
	app_dependencies = ['core.maniaplanet', 'core.trackmania']

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

		self.current_rankings = []
		self.points_repartition = []
		self.current_finishes = []
		self.widget = None

	async def on_start(self):
		# Register signals
		self.context.signals.listen(mp_signals.map.map_start, self.map_start)
		self.context.signals.listen(mp_signals.flow.round_start, self.round_start)
		self.context.signals.listen(tm_signals.finish, self.player_finish)
		self.context.signals.listen(tm_signals.waypoint, self.player_waypoint)
		self.context.signals.listen(mp_signals.player.player_connect, self.player_connect)
		self.context.signals.listen(tm_signals.give_up, self.player_giveup)
		self.context.signals.listen(tm_signals.scores, self.scores)

		# Make sure we move the multilap_info and disable the checkpoint_ranking and round_scores elements.
		self.instance.ui_manager.properties.set_visibility('checkpoint_ranking', False)
		self.instance.ui_manager.properties.set_visibility('round_scores', False)
		self.instance.ui_manager.properties.set_attribute('multilap_info', 'pos', '107., 88., 5.')

		self.widget = LiveRankingsWidget(self)
		await self.widget.display()

		scores = None
		try:
			scores = await self.instance.gbx('Trackmania.GetScores')
		except:
			pass

		if scores:
			await self.handle_scores(scores['players'])
			await self.widget.display()

		await self.get_points_repartition()

	def is_mode_supported(self, mode):
		mode = mode.lower()
		return mode.startswith('timeattack') or mode.startswith('rounds') or mode.startswith('team') or \
			   mode.startswith('laps') or mode.startswith('cup')

	async def scores(self, section, players, **kwargs):
		if section == 'PreEndRound':
			# Do not update the live rankings on the 'pre end round'-stage.
			# This will make the points added disappear without updating the actual scores.
			return

		await self.handle_scores(players)
		await self.widget.display()

	async def handle_scores(self, players):
		self.current_rankings = []
		self.current_finishes = []

		current_script = (await self.instance.mode_manager.get_current_script()).lower()
		if 'timeattack' in current_script:
			for player in players:
				if 'best_race_time' in player:
					if player['best_race_time'] != -1:
						new_ranking = dict(login=player['player'].login, nickname=player['player'].nickname, score=player['best_race_time'])
						self.current_rankings.append(new_ranking)
				elif 'bestracetime' in player:
					if player['bestracetime'] != -1:
						new_ranking = dict(login=player['login'], nickname=player['name'], score=player['bestracetime'])
						self.current_rankings.append(new_ranking)

			self.current_rankings.sort(key=lambda x: x['score'])
		elif 'rounds' in current_script or 'team' in current_script or 'cup' in current_script:
			for player in players:
				if 'map_points' in player:
					if player['map_points'] != -1:
						new_ranking = dict(login=player['player'].login, nickname=player['player'].nickname, score=player['map_points'], points_added=0)
						self.current_rankings.append(new_ranking)
				elif 'mappoints' in player:
					if player['mappoints'] != -1:
						new_ranking = dict(login=player['login'], nickname=player['name'], score=player['mappoints'], points_added=0)
						self.current_rankings.append(new_ranking)

			self.current_rankings.sort(key=lambda x: x['score'])
			self.current_rankings.reverse()

	async def map_start(self, map, restarted, **kwargs):
		self.current_rankings = []
		self.current_finishes = []
		await self.get_points_repartition()
		await self.widget.display()

	async def round_start(self, count, time):
		await self.get_points_repartition()

	async def player_connect(self, player, is_spectator, source, signal):
		await self.widget.display(player=player)

	async def player_giveup(self, time, player, flow):
		if 'Laps' not in await self.instance.mode_manager.get_current_script():
			return

		current_rankings = [x for x in self.current_rankings if x['login'] == player.login]
		if len(current_rankings) > 0:
			current_ranking = current_rankings[0]
			current_ranking['giveup'] = True

		await self.widget.display()

	async def player_waypoint(self, player, race_time, flow, raw):
		if 'laps' not in (await self.instance.mode_manager.get_current_script()).lower():
			return

		current_rankings = [x for x in self.current_rankings if x['login'] == player.login]
		if len(current_rankings) > 0:
			current_ranking = current_rankings[0]
			current_ranking['score'] = raw['racetime']
			current_ranking['cps'] = (raw['checkpointinrace'] + 1)
			current_ranking['best_cps'] = (self.current_rankings[0]['cps'])
			current_ranking['finish'] = raw['isendrace']
			current_ranking['cp_times'] = raw['curracecheckpoints']
			current_ranking['giveup'] = False
		else:
			best_cps = 0
			if len(self.current_rankings) > 0:
				best_cps = (self.current_rankings[0]['cps'])
			new_ranking = dict(login=player.login, nickname=player.nickname, score=raw['racetime'], cps=(raw['checkpointinrace'] + 1), best_cps=best_cps, cp_times=raw['curracecheckpoints'], finish=raw['isendrace'], giveup=False)
			self.current_rankings.append(new_ranking)

		self.current_rankings.sort(key=lambda x: (-x['cps'], x['score']))
		await self.widget.display()

	async def player_finish(self, player, race_time, lap_time, cps, flow, raw, **kwargs):
		current_script = (await self.instance.mode_manager.get_current_script()).lower()
		if 'laps' in current_script:
			await self.player_waypoint(player, race_time, flow, raw)
			return

		if 'timeattack' in current_script:
			current_rankings = [x for x in self.current_rankings if x['login'] == player.login]
			score = lap_time
			if len(current_rankings) > 0:
				current_ranking = current_rankings[0]

				if score < current_ranking['score']:
					current_ranking['score'] = score
					self.current_rankings.sort(key=lambda x: x['score'])
					await self.widget.display()
			else:
				new_ranking = dict(login=player.login, nickname=player.nickname, score=score)
				self.current_rankings.append(new_ranking)
				self.current_rankings.sort(key=lambda x: x['score'])
				await self.widget.display()

			return

		if 'rounds' in current_script or 'team' in current_script or 'cup' in current_script:
			new_finish = dict(login=player.login, nickname=player.nickname, score=race_time)
			self.current_finishes.append(new_finish)

			new_finish_rank = len(self.current_finishes) - 1
			new_finish['points_added'] = self.points_repartition[new_finish_rank] \
				if len(self.points_repartition) > new_finish_rank \
				else self.points_repartition[(len(self.points_repartition) - 1)]

			current_ranking = next((item for item in self.current_rankings if item['login'] == player.login), None)
			if current_ranking is not None:
				current_ranking['points_added'] = new_finish['points_added']
			else:
				new_finish['score'] = 0
				self.current_rankings.append(new_finish)

			self.current_rankings.sort(key=lambda x: (-x['score'], -x['points_added']))
			await self.widget.display()
			return

	async def get_points_repartition(self):
		current_script = (await self.instance.mode_manager.get_current_script()).lower()
		if 'rounds' in current_script or 'team' in current_script or 'cup' in current_script:
			points_repartition = await self.instance.gbx('Trackmania.GetPointsRepartition')
			self.points_repartition = points_repartition['pointsrepartition']
		else:
			# Reset the points repartition array.
			self.points_repartition = []
			self.current_finishes = []
