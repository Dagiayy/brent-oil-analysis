import React from 'react';

const StatsCard = ({ stats }) => {
  if (!stats.total) return null;
  return (
    <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem' }}>
      {[
        ['Avg Return', stats.avg_return],
        ['Volatility', stats.volatility],
        ['Data Points', stats.total],
      ].map(([label, value]) =>
        <div key={label} style={{ flex: 1, padding: '1rem', background: '#f4f4f4', borderRadius: 8 }}>
          <h4>{label}</h4>
          <p>{typeof value==='number' ? value.toFixed(4) : value}</p>
        </div>
      )}
    </div>
  );
};

export default StatsCard;
