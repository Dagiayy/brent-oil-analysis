import React from 'react';
import { Card } from 'react-bootstrap';

const StatsCard = ({ title, value }) => (
  <Card className="text-center shadow-sm" style={{ minHeight: 100 }}>
    <Card.Body>
      <Card.Title style={{ fontSize: '1.2rem' }}>{title}</Card.Title>
      <Card.Text style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{value ?? 'N/A'}</Card.Text>
    </Card.Body>
  </Card>
);

export default StatsCard;
