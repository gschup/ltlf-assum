def dfs(graph, node, prob, reach_dict, path=''):
    if graph.nodes[node]['player'] != 0:
        assert node not in reach_dict.keys(), 'multiple probabilistic paths to the same state!' + str(node)
        reach_dict[node] = prob
        return

    for succ in graph.successors(node):
        p = graph.edges[node, succ]['prob']
        dfs(graph, succ, p*prob, reach_dict, path=path+' ## '+str(node))


def write_prism_model(synth, name=''):
    file_name = 'data/%s.prism' % name
    p1_actions = []
    p2_actions = []
    transitions = ''
    # number of states excludes probabilistic states
    num_states = sum(n[1]['player'] != 0 for n in synth.nodes(data=True)) - 1
    state_id = 1
    state_ids = {}
    synth_init = synth.graph['init']
    state_ids[synth_init] = 0

    for node in synth.nodes():
        # probabilistic states are encoded in player 1 and 2 transitions
        if synth.nodes[node]['player'] == 0:
            continue

        assert synth.nodes[node]['player'] in [1, 2], 'node is neither player 0,1 or 2!'
        # id of the originating state
        if node not in state_ids.keys():
            state_ids[node] = state_id
            state_id += 1
        node_id = state_ids[node]

        # each successor represents a choice
        for i, succ in enumerate(synth.successors(node)):
            if synth.nodes[node]['player'] == 1:
                action_guard = '[p1_%i_%s]' % (node_id, synth.edges[node, succ]['act'])
                p1_actions.append(action_guard)
            else:
                action_guard = '[p2_%i_%i]' % (node_id, i)
                p2_actions.append(action_guard)
            transition_str = '  %s x=%i -> ' % (action_guard, node_id)
            reach_dict = {}
            # depth-first-search for path through probabilistic states
            dfs(synth, succ, 1, reach_dict)

            if len(reach_dict) == 0:
                print("Synth game state", succ, "has no reachable successors, this is a construction error...")
                for succsucc in synth.successors(succ):
                    print(succsucc)
                continue

            for reach_node, reach_prob in reach_dict.items():
                if reach_node not in state_ids.keys():
                    state_ids[reach_node] = state_id
                    state_id += 1
                reach_node_id = state_ids[reach_node]
                transition_str += '%f : (x\'=%i) + ' % (reach_prob, reach_node_id)
            transition_str = transition_str[:-3] + ';\n'
            transitions += transition_str

    assert len(synth.graph['acc']) > 0, '<write_prism_model> There are no accepting states!'

    reach_cond = '('
    for acc_state in synth.graph['acc']:
        acc_id = state_ids[acc_state]
        reach_cond += 'x=%i | ' % acc_id
    reach_cond = reach_cond[:-3] + ')'

    # actually write the file
    prism_file = open(file_name, 'w')

    # Header
    prism_file.write('//synthesis game in PRISM-games language, generated from networkx digraph model \n\n')
    prism_file.write('smg \n\n')

    # player 1
    prism_file.write('player p1 \n')
    p1_action_str = ''
    for action in p1_actions:
        p1_action_str += '  ' + action + ',\n'
    prism_file.write(p1_action_str[:-2] + '\n')
    prism_file.write('endplayer \n\n')

    # player 2
    prism_file.write('player p2 \n')
    p2_action_str = ''
    for action in p2_actions:
        p2_action_str += '  ' + action + ',\n'
    prism_file.write(p2_action_str[:-2] + '\n')
    prism_file.write('endplayer \n\n')

    # label accepting states
    prism_file.write('label "accept" = %s ;\n\n' % reach_cond)

    # module
    prism_file.write('module %s \n' % name)
    prism_file.write('  x : [0..%i] init 0;\n\n' % num_states)
    prism_file.write(transitions + '\n')
    prism_file.write('endmodule \n\n')

    prism_file.close()

    return file_name, state_ids
