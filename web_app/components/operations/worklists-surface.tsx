'use client';
import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { MetricCard, Card } from '@/components/ui/card';
import { FilterBar } from '@/components/ui/filter-bar';
import { ExplainabilityBlock } from '@/components/ui/explainability-block';
import { WorklistList } from '@/components/ui/worklist-list';
import { apiFetch } from '@/lib/api/client';
import type { WorklistItem, ListResponse } from '@/lib/api/contracts';
import { normalizeListResponse } from '@/lib/api/contracts';
import { pathLabels } from '@/lib/navigation';

export function WorklistsSurface(){const [data,setData]=useState<ListResponse<WorklistItem>|null>(null);const [query,setQuery]=useState('');const [error,setError]=useState<string|null>(null);useEffect(()=>{void apiFetch<ListResponse<WorklistItem>>('/worklists').then(res=>setData(normalizeListResponse(res))).catch(err=>setError(err instanceof Error?err.message:'Ошибка загрузки задач'))},[]); const items=useMemo(()=>{const rows=data?.items||[]; if(!query)return rows; return rows.filter(item=>JSON.stringify(item).toLowerCase().includes(query.toLowerCase()))},[data,query]); const open=items.filter(item=>item.status!=='done'&&item.status!=='cancelled').length; const overdue=items.filter(item=>item.is_overdue&&item.status!=='done'&&item.status!=='cancelled').length; return <div className="grid"><div className="topbar"><div><h1 className="page-title">{pathLabels['/worklists']}</h1><p className="page-subtitle">Ежедневные очереди задач с привязкой к действиям и объяснениям.</p></div></div><FilterBar placeholder="Фильтр по ферме, задаче, исполнителю или алерту…" onChange={setQuery} /><div className="grid grid-3"><MetricCard title="Всего задач" value={items.length} /><MetricCard title="Открытых задач" value={open} /><MetricCard title="Просроченных" value={overdue} /></div><ExplainabilityBlock reasons={['Рабочие списки управляются сервером и аудируются.','React отображает только канонические DTO и хуки действий.','Контексты одной и нескольких ферм отражаются через ссылки на сущности.']} />{error?<div className="card error-text">{error}</div>:null}{!data?<div className="card">Загружаю задачи…</div>:null}{data?<><WorklistList items={items.slice(0,10)} /><Card><h3 className="card-title">Связанные действия</h3><div className="linked-inline-actions"><Link href="/timeline">Открыть планировщик</Link><Link href="/decisions">Журнал решений</Link><Link href="/support">Обратная связь / поддержка</Link></div></Card></>:null}</div>}
