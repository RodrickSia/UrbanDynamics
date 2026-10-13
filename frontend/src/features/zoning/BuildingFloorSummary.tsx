import type { ProposedBuilding } from './developmentTypes';

const uses: Record<string, string> = { residential: 'Residential', commercial: 'Commercial', office: 'Office', other: 'Other' };
export function BuildingFloorSummary({ building }: { building: ProposedBuilding }) {
  if (!building.floor_stack?.length) return null;
  return <details open><summary>Floor uses</summary>
    <div className="development-floor-table zoning-table-scroll"><table>
      <thead><tr><th>Floor</th><th>Use</th><th>Height</th><th>GFA</th><th>FAR</th></tr></thead>
      <tbody>{building.floor_stack.map(floor => <tr key={floor.floor}>
        <th>{floor.floor}</th><td>{uses[floor.space_use_id] ?? floor.space_use_id}</td><td>{floor.floor_height} m</td>
        <td aria-label={floor.counts_gfa ? 'Included' : 'Excluded'}>{floor.counts_gfa ? '✓' : '—'}</td>
        <td aria-label={floor.counts_far ? 'Included' : 'Excluded'}>{floor.counts_far ? '✓' : '—'}</td>
      </tr>)}</tbody>
    </table></div>
  </details>;
}
