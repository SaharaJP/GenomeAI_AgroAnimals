import { Card } from '@/components/ui/card';

export type ParityEvidenceRow={legacySurface:string;reactSurface:string;parityLevel:string;backendContract:string;notes:string};
export function ParityEvidenceTable({rows}:{rows:ParityEvidenceRow[]}){return <Card><h3 className="card-title">Measured parity evidence</h3><div className="table-wrap"><table className="table"><thead><tr><th>Legacy surface</th><th>React surface</th><th>Parity level</th><th>Backend contract</th><th>Notes</th></tr></thead><tbody>{rows.map(row=><tr key={`${row.legacySurface}-${row.reactSurface}`}><td>{row.legacySurface}</td><td>{row.reactSurface}</td><td>{row.parityLevel}</td><td>{row.backendContract}</td><td>{row.notes}</td></tr>)}</tbody></table></div></Card>}
