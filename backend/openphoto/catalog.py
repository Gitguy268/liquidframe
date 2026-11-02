"""Shared query, metadata, selection, album and reversible action services."""
import datetime,json,re,sqlite3
from pathlib import Path
from . import store
from .workspaces import PRIVATE

EDITABLE={'title','caption','keywords','rating','pick_state','color_label','favorite','hidden','deleted_at','purged','captured','latitude','longitude','place','user_meta'}

def visibility(view='library',alias=''):
    p=alias+'.' if alias else ''
    if view in ['hidden','trash'] and not PRIVATE.get():raise PermissionError('Unlock private views first.')
    if view=='trash':return f'{p}deleted_at IS NOT NULL AND {p}purged=0'
    if view=='hidden':return f'{p}hidden=1 AND {p}deleted_at IS NULL AND {p}purged=0'
    return f'{p}hidden=0 AND {p}deleted_at IS NULL AND {p}purged=0'

def normalize(a):
    for k,default in [('metadata',{}),('keywords',[]),('user_meta',{})]:
        if isinstance(a.get(k),str):a[k]=json.loads(a[k] or json.dumps(default))
    a.pop('canonical_path',None)
    return a

FIELDS={'filename':'name','name':'name','title':'title','caption':'caption','description':'caption','keyword':'keywords','keywords':'keywords','date':'captured','date_added':'imported_at','date_edited':'edited_at','rating':'rating','camera':'camera','lens':'lens','iso':'iso','aperture':'aperture','focal_length':'focal_length','shutter':'shutter','flash':'flash','place':'place','format':'extension','kind':'media_kind','favorite':'favorite','hidden':'hidden','pick':'pick_state','color':'color_label','text':'ocr_text'}

def condition(rule,args):
    field=rule.get('field');op=rule.get('operator','contains');v=rule.get('value','')
    if field in ['album','person']:
        table,col=('album_assets','album_id') if field=='album' else ('faces','person_id')
        args.append(v);return f'id {"NOT IN" if op in ["is_not","not_contains"] else "IN"} (SELECT asset_id FROM {table} WHERE {col}=?)'
    col=FIELDS.get(field)
    if not col:raise ValueError('Unknown smart-album field.')
    if op in ['is','is_not','greater','less','before','after']:
        args.append(v);return col+{'is':' = ?','is_not':' != ?','greater':' > ?','less':' < ?','before':' < ?','after':' > ?'}[op]
    if op in ['contains','not_contains','starts_with']:
        args.append((str(v)+'%') if op=='starts_with' else '%'+str(v)+'%');return col+(' NOT LIKE ?' if op=='not_contains' else ' LIKE ?')
    if op=='range':
        if not isinstance(v,list) or len(v)!=2:raise ValueError('A range needs two values.')
        args.extend(v);return col+' BETWEEN ? AND ?'
    if op=='last':
        days=min(36500,max(1,int(v)));cut=store.now()-days*86400
        args.append(datetime.datetime.fromtimestamp(cut).isoformat() if col=='captured' else cut);return col+' >= ?'
    raise ValueError('Unknown smart-album operator.')

def where(query):
    q=query or {};view=q.get('view','library');parts=[visibility(view)];args=[]
    for field in ['root_id','stack_id','media_kind','import_id']:
        if q.get(field):parts.append(field+'=?');args.append(q[field])
    if q.get('favorite') or view=='favorites':parts.append('favorite=1')
    if q.get('format'):parts.append('extension=?');args.append(q['format'].lower())
    if q.get('date_from'):parts.append('captured>=?');args.append(q['date_from'])
    if q.get('date_to'):parts.append('captured<=?');args.append(q['date_to']+'T23:59:59')
    if q.get('rating') is not None:parts.append('rating>=?');args.append(int(q['rating']))
    if q.get('person_id'):parts.append('id IN (SELECT asset_id FROM faces WHERE person_id=? AND rejected=0 UNION SELECT asset_id FROM observations WHERE person_id=?)');args.extend([q['person_id'],q['person_id']])
    if q.get('album_id'):
        album=store.one('SELECT * FROM albums WHERE id=?',(q['album_id'],))
        if not album:raise ValueError('Album not found.')
        if album['kind']=='smart':
            rules=json.loads(album['rules']);rows=rules.get('conditions',[])
            if len(rows)>64:raise ValueError('Use at most 64 smart album conditions.')
            terms=[condition(r,args) for r in rows]
            if terms:parts.append('('+(' OR ' if rules.get('match')=='any' else ' AND ').join(terms)+')')
        else:parts.append('id IN (SELECT asset_id FROM album_assets WHERE album_id=?)');args.append(album['id'])
    for key,column in [('edited','edited_at'),('viewed','viewed_at'),('exported','exported_at')]:
        if view==key:parts.append(column+' IS NOT NULL')
    if view=='raw':parts.append("extension IN ('arw','cr2','cr3','dng','nef','raf','rw2','orf','pef')")
    if view=='animated':parts.append("extension IN ('gif','apng')")
    if view=='video':parts.append("media_kind='video'")
    if view=='screenshots':parts.append("(LOWER(name) LIKE '%screenshot%' OR LOWER(name) LIKE '%screen shot%')")
    if view in ['live','burst']:parts.append('stack_id IN (SELECT id FROM stacks WHERE kind=?)');args.append(view)
    if q.get('collection_id'):parts.append('id IN (SELECT value FROM json_each((SELECT assets FROM collections WHERE id=?)))');args.append(q['collection_id'])
    rows=q.get('conditions',[])
    if len(rows)>64:raise ValueError('Use at most 64 conditions.')
    if rows:parts.append('('+(' OR ' if q.get('match')=='any' else ' AND ').join(condition(r,args) for r in rows)+')')
    text=q.get('q','').strip()
    if text and not q.get('semantic'):
        tokens=re.findall(r'[\w]+',text,re.UNICODE)
        if tokens:parts.append('id IN (SELECT asset_id FROM asset_text WHERE asset_text MATCH ?)');args.append(' AND '.join('"'+t+'"*' for t in tokens))
    if text and q.get('semantic'):
        from . import library
        ranked=q.get('_ranking') or library.semantic_search(text);ids=[r['id'] for r in ranked]
        parts.append('id IN ('+','.join('?' for _ in ids)+')' if ids else '0');args.extend(ids)
    if q.get('collapse_stacks',True) and not q.get('stack_id') and view not in ['trash','hidden']:
        parts.append('(stack_id IS NULL OR id=(SELECT primary_id FROM stacks WHERE stacks.id=assets.stack_id))')
    return ' AND '.join(parts),args

def query_order(q):
    ranking=q.get('_ranking',[])
    order={'newest':'captured DESC,id','oldest':'captured,id','name':"COALESCE(NULLIF(title,''),name) COLLATE NOCASE,id",'rating':'rating DESC,captured DESC,id','custom':'(SELECT position FROM album_assets WHERE asset_id=assets.id AND album_id=?),id'}.get(q.get('sort','newest'),'captured DESC,id')
    args=[q.get('album_id')] if q.get('sort')=='custom' else []
    if ranking:
        order='CASE id '+''.join('WHEN ? THEN '+str(n)+' ' for n,r in enumerate(ranking))+'ELSE 100000 END,id'
        args=[r['id'] for r in ranking]
    return order,args

def prepare_query(q):
    q=dict(q or {})
    if q.get('q') and q.get('semantic') and '_ranking' not in q:
        from . import library
        q['_ranking']=library.semantic_search(q['q'])
    return q

def query(q=None,offset=0,limit=120):
    q=prepare_query(q);ranking=q.get('_ranking',[])
    clause,args=where(q);limit=max(1,min(240,int(limit)));offset=max(0,int(offset))
    order,orderargs=query_order(q)
    values=store.rows('SELECT assets.*,COALESCE((SELECT version FROM recipes WHERE asset_id=assets.id),0) recipe_version,(SELECT COUNT(*) FROM assets s WHERE s.stack_id=assets.stack_id) stack_count FROM assets WHERE '+clause+' ORDER BY '+order+' LIMIT ? OFFSET ?',[*args,*orderargs,limit,offset])
    total=store.one('SELECT COUNT(*) n FROM assets WHERE '+clause,args)['n']
    groups=store.rows('SELECT substr(captured,1,7) date,COUNT(*) count FROM assets WHERE '+clause+' GROUP BY substr(captured,1,7) ORDER BY date '+('ASC' if q.get('sort')=='oldest' else 'DESC'),args) if offset==0 and q.get('sort','newest') in ['newest','oldest'] and not ranking else []
    byid={r['id']:r for r in ranking}
    for a in values:
        if 'match_time' in byid.get(a['id'],{}):a['match_time']=byid[a['id']]['match_time']
    return {'assets':[normalize(a) for a in values],'total':total,'groups':groups}

def ids(selection):
    if isinstance(selection,list):return selection
    if selection.get('selection_id'):
        excluded=set(selection.get('exclude_ids',[]));return [r['asset_id'] for r in store.rows('SELECT asset_id FROM selection_items WHERE selection_id=?',(selection['selection_id'],)) if r['asset_id'] not in excluded]
    return selection.get('ids',[])

def snapshot(query_spec):
    clause,args=where(query_spec);i=store.uid()
    with store.db() as c:
        c.execute('INSERT INTO selections VALUES(?,?,?)',(i,store.now(),json.dumps(query_spec)))
        c.execute('INSERT INTO selection_items SELECT ?,id,revision FROM assets WHERE '+clause,[i,*args])
        count=c.execute('SELECT COUNT(*) FROM selection_items WHERE selection_id=?',(i,)).fetchone()[0]
    return {'selection_id':i,'count':count}

def journal(label,before,after,connection=None):
    from contextlib import nullcontext
    with (nullcontext(connection) if connection is not None else store.db()) as c:
        c.execute('DELETE FROM action_history WHERE undone=1')
        c.execute('INSERT INTO action_history VALUES(?,?,?,?,0,?)',(store.uid(),label,json.dumps(before),json.dumps(after),store.now()))

def patch_assets(selection,changes,label='Change metadata'):
    chosen=ids(selection)
    if len(chosen)>100000:raise ValueError('Selection is too large.')
    if set(changes)-EDITABLE:raise ValueError('Unsupported metadata field.')
    if 'rating' in changes and not 0<=int(changes['rating'])<=5:raise ValueError('Rating must be 0–5.')
    if 'keywords' in changes:
        if not isinstance(changes['keywords'],list) or len(changes['keywords'])>500:raise ValueError('Keywords must be a list.')
        changes['keywords']=json.dumps(list(dict.fromkeys(str(k)[:150] for k in changes['keywords'])))
    for key in ['title','caption','place']:
        if key in changes and len(str(changes[key]))>10000:raise ValueError('Metadata text is too long.')
    if changes.get('hidden') and not store.setting('private_passcode'):raise ValueError('Set a private-view passcode in Settings before hiding items.')
    if changes.get('pick_state') not in [None,'','none','pick','reject']:raise ValueError('Choose none, pick or reject.')
    if changes.get('color_label'):changes['color_label']=changes['color_label'].lower()
    if changes.get('color_label') not in [None,'','red','orange','yellow','green','blue','purple']:raise ValueError('Unknown color label.')
    for key,limit in [('latitude',90),('longitude',180)]:
        if changes.get(key) is not None and abs(float(changes[key]))>limit:raise ValueError('Invalid coordinates.')
    before=[];after=[]
    with store.db() as c:
        for i in chosen:
            a=store.get_asset(i);previous={k:c.execute('SELECT '+k+' FROM assets WHERE id=?',(i,)).fetchone()[0] for k in changes}
            meta=json.loads(c.execute('SELECT user_meta FROM assets WHERE id=?',(i,)).fetchone()[0] or '{}');previous['user_meta']=json.dumps(meta);meta.setdefault('original',{});meta.setdefault('overrides',{})
            for k,v in changes.items():
                if k not in ['hidden','deleted_at','purged','user_meta']:
                    meta['original'].setdefault(k,a.get(k));meta['overrides'][k]=v
            effective={**changes,'user_meta':json.dumps(meta)}
            before.append({'table':'assets','id':i,'values':previous});after.append({'table':'assets','id':i,'values':effective})
            if changes:c.execute('UPDATE assets SET '+','.join(k+'=?' for k in effective)+' WHERE id=?',[*effective.values(),i])
        if before:journal(label,before,after,c)
    return {'updated':len(chosen)}

def history_action(redo=False):
    action=store.one('SELECT * FROM action_history WHERE undone=? ORDER BY created '+('ASC' if redo else 'DESC')+' LIMIT 1',(int(redo),))
    if not action:raise ValueError('Nothing to '+('redo' if redo else 'undo')+'.')
    changes=json.loads(action['after_state' if redo else 'before_state'])
    for change in changes:
        if change['table']=='assets':store.get_asset(change['id'])
        elif change['table']=='album_assets':
            a=store.one('SELECT id,hidden,deleted_at,purged FROM assets WHERE id=?',(change['key']['asset_id'],))
            if a and (a['hidden'] or a['deleted_at'] or a['purged']) and not PRIVATE.get():raise PermissionError('Unlock private views before undoing this action.')
    with store.db() as c:
        for change in changes:
            table=change['table'];fields=change['values']
            if table=='assets':
                if set(fields)-EDITABLE:raise ValueError('Invalid history fields.')
                c.execute('UPDATE assets SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',[*fields.values(),change['id']]);continue
            if table not in HISTORY_TABLES:raise ValueError('Invalid history entry.')
            key=change['key']
            if not key or set(key)-HISTORY_TABLES[table]:raise ValueError('Invalid history key.')
            if fields is None:c.execute('DELETE FROM '+table+' WHERE '+' AND '.join(k+'=?' for k in key),list(key.values()))
            else:
                if set(fields)-HISTORY_TABLES[table]:raise ValueError('Invalid history fields.')
                columns=list(fields);c.execute('INSERT INTO '+table+'('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+') ON CONFLICT DO UPDATE SET '+','.join(k+'=excluded.'+k for k in columns),list(fields.values()))
        c.execute('UPDATE action_history SET undone=? WHERE id=?',(int(not redo),action['id']))
    return {'label':action['label']}

def remove(selection,permanent=False):
    return patch_assets(selection,{'purged':1} if permanent else {'deleted_at':store.now()},'Remove permanently from catalog' if permanent else 'Move to Recently Deleted')

def expire():store.execute('UPDATE assets SET purged=1 WHERE deleted_at IS NOT NULL AND deleted_at<?',(store.now()-30*86400,))

def period_covers(q,unit='month'):
    clause,args=where(q);size=4 if unit=='year' else 7
    rows=store.rows(f'''WITH visible AS (SELECT *,substr(captured,1,{size}) period FROM assets WHERE {clause}), ranked AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY period ORDER BY favorite DESC,rating DESC,quality DESC,width*height DESC,id) rank,COUNT(*) OVER(PARTITION BY period) count FROM visible) SELECT id,name,title,captured,period,count,revision,media_kind FROM ranked WHERE rank=1 ORDER BY period DESC''',args)
    overrides=store.setting('period_covers',{})
    for row in rows:
        key=unit+':'+row['period']
        if key in overrides:
            a=store.one('SELECT id FROM assets WHERE id=? AND '+visibility(),(overrides[key],))
            if a:row['id']=a['id']
    return rows

def create_album(body):
    name=str(body.get('name','')).strip()
    if not name:raise ValueError('Name is required.')
    if body.get('kind')=='smart':where({'conditions':body.get('rules',{}).get('conditions',[])})
    i=store.uid()
    with store.db() as c:
        c.execute('INSERT INTO albums(id,name,created,folder_id,kind,rules) VALUES(?,?,?,?,?,?)',(i,name,store.now(),body.get('folder_id'),body.get('kind','album'),json.dumps(body.get('rules',{}))))
        after=dict(c.execute('SELECT * FROM albums WHERE id=?',(i,)).fetchone());journal('Create album',[row_change('albums',{'id':i},None)],[row_change('albums',{'id':i},after)],c)
    if body.get('selection'):album_items(i,body['selection'])
    return {'id':i,'name':name}

def album_items(album_id,selection,remove=False):
    chosen=ids(selection)
    if not store.one('SELECT id FROM albums WHERE id=?',(album_id,)):raise ValueError('Album not found.')
    before=[];after=[]
    with store.db() as c:
        for n,i in enumerate(chosen):
            store.get_asset(i)
            old=c.execute('SELECT * FROM album_assets WHERE album_id=? AND asset_id=?',(album_id,i)).fetchone();before.append(row_change('album_assets',{'album_id':album_id,'asset_id':i},dict(old) if old else None))
            if remove:c.execute('DELETE FROM album_assets WHERE album_id=? AND asset_id=?',(album_id,i))
            else:c.execute('INSERT OR IGNORE INTO album_assets(album_id,asset_id,position) VALUES(?,?,?)',(album_id,i,n+store.now()))
            row=c.execute('SELECT * FROM album_assets WHERE album_id=? AND asset_id=?',(album_id,i)).fetchone();after.append(row_change('album_assets',{'album_id':album_id,'asset_id':i},dict(row) if row else None))
        journal('Remove from album' if remove else 'Add to album',before,after,c)
    return {'updated':len(chosen)}

def stack(selection,kind='manual',primary=None):
    chosen=ids(selection)
    if len(chosen)<2:raise ValueError('Select at least two items.')
    for i in chosen:store.get_asset(i)
    if primary and primary not in chosen:raise ValueError('Primary item must be in the stack.')
    i=store.uid();store.execute('INSERT INTO stacks(id,kind,primary_id) VALUES(?,?,?)',(i,kind,primary or chosen[0]))
    with store.db() as c:c.executemany('UPDATE assets SET stack_id=? WHERE id=?',[(i,a) for a in chosen])
    return {'id':i}

def duplicate_merge(chosen,winner):
    if winner not in chosen:raise ValueError('Choose the version to keep.')
    values=[store.get_asset(i) for i in chosen];keep=next(a for a in values if a['id']==winner)
    keywords=list(dict.fromkeys(k for a in values for k in a['keywords']))
    result=patch_assets([winner],{'keywords':keywords,'favorite':int(any(a['favorite'] for a in values)),'rating':max(a['rating'] for a in values)},'Merge duplicate metadata')
    with store.db() as c:
        for a in values:c.execute('INSERT OR IGNORE INTO album_assets(album_id,asset_id) SELECT album_id,? FROM album_assets WHERE asset_id=?',(winner,a['id']))
    remove([i for i in chosen if i!=winner]);return result


def people(include_hidden=False):
    return store.rows("SELECT p.*,COUNT(DISTINCT r.asset_id) count,COALESCE(p.cover_id,MIN(r.asset_id)) cover FROM people p JOIN (SELECT person_id,asset_id FROM faces WHERE rejected=0 UNION SELECT person_id,asset_id FROM observations WHERE person_id IS NOT NULL) r ON r.person_id=p.id JOIN assets a ON a.id=r.asset_id WHERE "+visibility(alias='a')+("" if include_hidden else " AND p.hidden=0")+" GROUP BY p.id ORDER BY p.favorite DESC,count DESC")

HISTORY_TABLES={'roots':{'id','path','name','kind','created'},'albums':{'id','name','created','folder_id','kind','rules','cover_id','sort','position'},'album_folders':{'id','name','parent_id','position'},'album_assets':{'album_id','asset_id','position'},'stacks':{'id','kind','primary_id'},'people':{'id','name','favorite','hidden','feature_less','cover_id','kind','position','group_id'}}

def row_change(table,key,values):return {'table':table,'key':key,'values':values}

def album_mutation(i,changes=None,delete=False):
    with store.db() as c:
        old=c.execute('SELECT * FROM albums WHERE id=?',(i,)).fetchone()
        if not old:raise ValueError('Album not found.')
        old=dict(old);before=[row_change('albums',{'id':i},old)];after=[]
        if delete:
            members=[dict(r) for r in c.execute('SELECT * FROM album_assets WHERE album_id=?',(i,))]
            before.extend(row_change('album_assets',{'album_id':i,'asset_id':r['asset_id']},r) for r in members)
            after.extend(row_change('album_assets',{'album_id':i,'asset_id':r['asset_id']},None) for r in members)
            after.append(row_change('albums',{'id':i},None));c.execute('DELETE FROM albums WHERE id=?',(i,))
        else:
            if not changes or set(changes)-HISTORY_TABLES['albums'] or 'id' in changes:raise ValueError('Invalid album changes.')
            if changes.get('cover_id'):store.get_asset(changes['cover_id'])
            c.execute('UPDATE albums SET '+','.join(k+'=?' for k in changes)+' WHERE id=?',[*changes.values(),i]);after=[row_change('albums',{'id':i},{**old,**changes})]
        journal('Delete album' if delete else 'Change album',before,after,c)
    return {'ok':True}


def authorize_person(person_id):
    if not store.one('SELECT id FROM people WHERE id=?',(person_id,)):raise ValueError('Person or pet group not found.')
    if not PRIVATE.get() and store.one('SELECT a.id FROM assets a JOIN (SELECT asset_id FROM faces WHERE person_id=? UNION SELECT asset_id FROM observations WHERE person_id=?) r ON r.asset_id=a.id WHERE a.hidden=1 OR a.deleted_at IS NOT NULL OR a.purged=1 LIMIT 1',(person_id,person_id)):
        raise PermissionError('Unlock private views before changing a group with private items.')


def detach_root(root_id):
    root=store.one('SELECT * FROM roots WHERE id=?',(root_id,))
    if not root:raise ValueError('Folder is not connected.')
    assets=store.rows('SELECT id,deleted_at FROM assets WHERE root_id=?',(root_id,))
    for asset in assets:store.get_asset(asset['id'])
    before=[];after=[];now=store.now()
    with store.db() as connection:
        for asset in assets:
            if asset['deleted_at'] is not None:continue
            before.append({'table':'assets','id':asset['id'],'values':{'deleted_at':None}})
            after.append({'table':'assets','id':asset['id'],'values':{'deleted_at':now}})
            connection.execute('UPDATE assets SET deleted_at=? WHERE id=?',(now,asset['id']))
        before.append(row_change('roots',{'id':root_id},root))
        after.append(row_change('roots',{'id':root_id},{**root,'kind':'detached'}))
        connection.execute("UPDATE roots SET kind='detached' WHERE id=?",(root_id,))
        journal('Disconnect folder',before,after,connection)
