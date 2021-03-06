import time
import sys
import pickle

from py4j.protocol import Py4JNetworkError

# OTHER CODE #
from ltlf2dfa_nx import LTLf2nxParser
from prismhandler.prism_handler import PrismHandler
from prismhandler.prism_io import write_prism_model
from safety_assumptions import minimal_safety_edges
from fairness_assumptions import minimal_fairness_edges
from advisers import simplest_adviser, AdviserType


class AdviserFramework:

    def __init__(self, agents):
        # PRISM API gateway
        try:
            self.prism_handler = PrismHandler()
            print('Successfully connected to PRISM java gateway!')
        except Py4JNetworkError as err:
            print('Py4JNetworkError:', err)
            print('It is most likely that you forgot to start the PRISM java gateway. '
                  'Compile and launch prismhandler/PrismEntryPoint.java!')
            sys.exit()

        self.ltlf_parser = LTLf2nxParser()
        self.agents = agents

    def complete_strategy_synthesis(self, results_path, compute_strategies=False, verbose=False):
        abs_start_time = time.time()
        self.create_synth_games()
        winnable = self.check_winnable()

        if all(winnable):
            print('No adviser computation necessary, winning strategies already exists!')
            if compute_strategies:
                print('Computing Strategies...\n')
                self.create_strategies()

                print('Pickling results into %s ...\n' % results_path)
                pickle.dump(self.agents, open(results_path, 'wb'))
            print('Took', time.time() - abs_start_time, 'seconds in total.\n')
            return time.time() - abs_start_time

        print('Winning strategy does not exist for some agents, will compute minimal assumptions.\n')

        fairness_changed = True
        fairness_rounds = 0
        while fairness_changed:
            fairness_rounds += 1
            print('#### Fairness Exchange Round %i\n' % fairness_rounds)
            safety_start_time = time.time()
            safety_changed = True
            safety_rounds = 0
            print('Beginning safety computations...\n')

            while safety_changed:
                safety_rounds += 1
                safety_changed = self.compute_and_exchange_safety()
                if safety_changed:
                    # create new synth games with new LTLf specs
                    self.create_synth_games()

            print('Safety converged after %i rounds.' % (safety_rounds - 1))
            print('Took', time.time() - safety_start_time, 'seconds.\n')

            print('Beginning fairness computations...\n')
            fairness_start_time = time.time()
            fairness_changed = self.compute_and_exchange_fairness()

            print('Computed and exchanged fairness advisers.')
            print('Took', time.time() - fairness_start_time, 'seconds.\n')

            if fairness_changed:
                self.create_synth_games()

            if verbose:
                print('AFTER FAIRNESS ROUND %i' % fairness_rounds)
                # safety print
                for agent in self.agents:
                    print('Safety Advisers for Agent %s:' % agent.name)
                    for adviser in agent.own_advisers:
                        if not adviser.adv_type == AdviserType.SAFETY:
                            continue

                        adviser.print_advice()
                    print('')
                # fairness print
                for agent in self.agents:
                    print('Fairness Advisers for Agent %s:' % agent.name)
                    for adviser in agent.own_advisers:
                        if not adviser.adv_type == AdviserType.FAIRNESS:
                            continue
                        adviser.print_advice()
                    print('')

        print('Fairness converged after %i rounds.' % (fairness_rounds - 1))
        print('Took', time.time() - abs_start_time, 'seconds.\n')

        winnable = self.check_winnable()
        if all(winnable):
            print('Adviser Computation successful, all agents have a winning strategy yielding all advisers!')

        if compute_strategies:
            print('Computing Strategies...\n')
            self.create_strategies()

            print('Pickling results into %s ...\n' % results_path)
            pickle.dump(self.agents, open(results_path, 'wb'))

        print('Total time elapsed:', time.time() - abs_start_time, '\n')
        return time.time() - abs_start_time

    def create_synth_games(self):
        start_time = time.time()
        for agent in self.agents:
            agent.create_dfa(self.ltlf_parser)  # update spec according to other safety advisers and create DFA
            agent.create_synthesis_game()  # create synthesis game
            agent.modify_game_own_advisers()  # modify game according to own safety and fairness advisers
            result = agent.modify_game_other_fairness()  # modify game according to fairness advisers from other agents
            agent.prune_unreachable_states()
            if not result:
                print('Agent', agent.name, 'cannot fulfill all fairness constraints. Negotiation failed.')
                sys.exit()

        print('Created synthesis games for all agents.')
        print('Took', time.time() - start_time, 'seconds. \n')

    def check_winnable(self, verbose=True):
        results = []
        # check if agents can win with the current game
        for agent in self.agents:
            prism_model, state_ids = write_prism_model(agent.synth, agent.name + '_win')
            self.prism_handler.load_model_file(prism_model)
            result = self.prism_handler.check_bool_property('<< p1 >> P>=1 [F \"accept\"]')
            results.append(result[0])
            if verbose:
                print('Agent %s has a winning strategy:' % agent.name, result[0])
        if verbose:
            print('')
        return results

    def create_strategies(self):
        for agent in self.agents:
            prism_model, state_ids = write_prism_model(agent.synth, agent.name + '_win')
            self.prism_handler.load_model_file(prism_model)
            strat = self.prism_handler.synthesize_strategy(path='../data/' + agent.name + '.strat',
                                                           property_string='<< p1 >> Pmax=? [F \"accept\"]')

            # remove player-2 recommendations from the strategy
            for state, state_id in state_ids.items():
                if agent.synth.nodes[state]['player'] != 1:
                    strat.pop(str(state_id), None)

            # save the strategy for the agent, but replace the state_ids with real state names
            agent.strategy = {}
            # this is okay because the mapping is unique in both directions
            inv_state_ids = {v: k for k, v in state_ids.items()}
            for state_id, act in strat.items():
                if act == '-':
                    # add "stay" as recommended action as the agent has fulfilled their goal
                    state = inv_state_ids[int(state_id)]
                    agent.strategy[state] = 'stay'
                else:
                    state = inv_state_ids[int(state_id)]
                    action = act.split('_')
                    agent.strategy[state] = action[2]

    def compute_and_exchange_fairness(self):
        fairness_changed = False
        for agent in self.agents:
            fairness_edges = minimal_fairness_edges(agent.synth, agent.name, self.prism_handler)
            sfa = simplest_adviser(agent.synth, fairness_edges, AdviserType.FAIRNESS)

            if len(sfa.adviser) > 0:
                fairness_changed = True
                agent.own_advisers.append(sfa)

                for other_agent in self.agents:
                    if agent.name == other_agent.name:
                        continue
                    # other_agent.check_fairness_feasibility(sfa)
                    other_agent.other_advisers.append(sfa)

        return fairness_changed

    def compute_and_exchange_safety(self):
        # SAFETY ASSUMPTIONS
        # call PRISM-games to compute cooperative safe set
        # then, compute simplest safety advisers
        # and save advisers if they are nonempty
        safety_changed = False

        for agent in self.agents:
            safety_edges = minimal_safety_edges(agent.synth, agent.name + '_safety', self.prism_handler)
            ssa = simplest_adviser(agent.synth, safety_edges, AdviserType.SAFETY)

            if len(ssa.adviser) > 0:
                safety_changed = True
                agent.own_advisers.append(ssa)

                for other_agent in self.agents:
                    if agent.name == other_agent.name:
                        continue

                    other_agent.add_other_adviser(ssa)

        return safety_changed
