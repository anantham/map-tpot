"""Read-only personalized recovery report and sourced candidate preview."""
from src.data.account_tag_queries import load_target_tag_anchors
from src.data.recovery_graph import BOUNDARY, load_recovery_graph, explain_recovery_paths
from src.graph.seed_recovery import METHODS, evaluate_recovery

LIMITS = ('No calibrated membership probabilities, precision or competence claims.',
    'Retrospective leave-one-IN-out; the hidden account keeps its edges but loses its label.',
    'All positives stay in denominators. Unjudged is unknown, not OUT. Tags overlap.',
    'No cross-tag inputs; NOT IN is evaluation only, never a ranking penalty.',
    'Recovery counts use the worst tied rank; possible counts use the best tied rank.',
    'Method comparison is exploratory, not a sealed future holdout or proof a cluster exists.')


def build_seed_recovery(relationship_path,index_path,tag_path,*,ego,tag,
        layer='follows',direction='outgoing',method='two_hop',limit=20,client=None,published_access=None):
    if not isinstance(ego,str) or not ego.strip() or not isinstance(tag,str) or not tag.strip():
        raise ValueError('ego and tag are required')
    if method not in METHODS:raise ValueError('Unknown recovery method')
    if type(limit) is not int or not 1<=limit<=25:raise ValueError('limit must be between1 and25')
    anchors = load_target_tag_anchors(tag_path,ego=ego.strip(),tag=tag)
    positive,negative = set(anchors.positive),set(anchors.negative)
    target = {'ego':ego.strip(),'tag':tag.strip(),'tagKey':tag.strip().casefold()}
    base = {'target':target,'layer':layer,'direction':direction,'method':method,
        'positiveCount':len(positive),'negativeCount':len(negative),'limits':list(LIMITS),
        'boundary':BOUNDARY,'candidates':[],'calibrated':False}
    view = load_recovery_graph(relationship_path,index_path,layer=layer,direction=direction,
        client=client,published_access=published_access)
    base.update(status=view['status'],source=view['source'])
    if view['status']!='available':return base
    graph = view['graph']
    base['coverage'] = {'nodes':len(graph.nodes),'directedPairs':len(graph.edges),
        'positiveWithIncidentEdges':len(positive & graph.nodes),
        'positiveWithWalkEdges':sum(bool(graph.adj.get(seed)) for seed in positive)}
    if len(positive)<3:
        base['status']='insufficient_examples'
        return base
    evaluation = evaluate_recovery(graph,positive,negative)
    for metrics in evaluation['methods'].values():
        for fold in metrics['folds']:
            fold.update(view['profiles'].get(fold['accountId'],{}))
    base['evaluation']=evaluation
    rows = graph.rank(positive,method)
    candidates = [row for row in rows if row['accountId'] not in negative]
    # OUT is not used by the ranker. Hide it only from the live unjudged queue;
    # the full-seed exposure metric and held-out rankings above retain it.
    base['candidateCount']=len(candidates)
    for row in candidates[:limit]:
        account = row['accountId']
        paths = graph.paths(positive,account,max_hops=2 if method=='two_hop' else 1)
        supporters = sum(bool(graph.paths([seed],account,
            max_hops=2 if method=='two_hop' else 1,limit=1)) for seed in positive)
        if method=='popularity':
            incoming = sorted((a,b) for a,b in graph.edges if b==account)
            paths = [[edge] for edge in incoming[:1]]
        base['candidates'].append({**row,**view['profiles'].get(account,{}),
            'supportingSeeds':supporters,'shownPaths':len(paths),
            'globalSupport':graph.popularity[account],
            'paths':explain_recovery_paths(view,paths)})
    return base
