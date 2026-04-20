import type { PropsWithChildren } from 'react';
export function Card({children}:PropsWithChildren){return <section className="card">{children}</section>}
export function MetricCard({title,subtitle,value}:{title:string;subtitle?:string;value:string|number}){return <Card><h3 className="card-title">{title}</h3>{subtitle?<p className="card-subtitle">{subtitle}</p>:null}<div className="card-value">{value}</div></Card>}
