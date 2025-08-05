import React, { useState } from 'react';
import { Container, Row, Col, Card, Spinner, Alert, Form, Button } from 'react-bootstrap';
import DatePicker from 'react-datepicker';
import 'react-datepicker/dist/react-datepicker.css';
import axios from 'axios';
import { Line } from 'react-chartjs-2';
import annotationPlugin from 'chartjs-plugin-annotation';

import {
  Chart as ChartJS,
  TimeScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
} from 'chart.js';

import 'chartjs-adapter-date-fns';

ChartJS.register(TimeScale, LinearScale, PointElement, LineElement, Tooltip, Legend, annotationPlugin);

function StatCard({ title, value }) {
  return (
    <Card className="text-center shadow-sm" style={{ minHeight: 100 }}>
      <Card.Body>
        <Card.Title style={{ fontSize: '1.2rem' }}>{title}</Card.Title>
        <Card.Text style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{value ?? 'N/A'}</Card.Text>
      </Card.Body>
    </Card>
  );
}

function ChartComponent({ data, changePoint, events }) {
  if (!data || !Array.isArray(data) || data.length === 0) return <p>No data available.</p>;

  const chartData = {
    labels: data.map((d) => new Date(d.Date)),
    datasets: [
      {
        label: 'Log Return',
        data: data.map((d) => d.Log_Return),
        borderColor: '#007bff',
        backgroundColor: 'rgba(0,123,255,0.2)',
        fill: true,
        pointRadius: 1,
        tension: 0.3,
      },
    ],
  };

  const annotations = changePoint && changePoint.data
    ? {
        changePointLine: {
          type: 'line',
          scaleID: 'x',
          value: new Date(changePoint.data.change_date),
          borderColor: 'red',
          borderWidth: 2,
          label: {
            enabled: true,
            content: 'Change Point',
            backgroundColor: 'rgba(255, 0, 0, 0.7)',
            color: '#fff',
            position: 'start',
          },
        },
      }
    : {};

  const options = {
    responsive: true,
    scales: {
      x: {
        type: 'time',
        time: {
          unit: 'month',
        },
        title: {
          display: true,
          text: 'Date',
        },
      },
      y: {
        title: {
          display: true,
          text: 'Log Return',
        },
      },
    },
    plugins: {
      annotation: {
        annotations,
      },
      tooltip: {
        callbacks: {
          afterBody: (ctx) => {
            const labelDate = new Date(ctx[0].label).setHours(0, 0, 0, 0);
            const event = events.find((ev) => {
              const eventDate = new Date(ev['Start Date']).setHours(0, 0, 0, 0);
              return eventDate === labelDate;
            });
            return event ? `Event: ${event.Event}` : '';
          },
        },
      },
      legend: {
        display: true,
        position: 'top',
      },
    },
  };

  return <Line data={chartData} options={options} />;
}

function App() {
  const [data, setData] = useState([]);
  const [changePoint, setChangePoint] = useState(null);
  const [stats, setStats] = useState({});
  const [events, setEvents] = useState([]);
  const [start, setStart] = useState(null);
  const [end, setEnd] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const fetchData = async () => {
    setLoading(true);
    setError('');
    try {
      const params = {};
      if (start) params.start = start.toISOString();
      if (end) params.end = end.toISOString();

      const [pricesRes, changePointRes, eventsRes, statsRes] = await Promise.all([
        axios.get('http://localhost:5000/api/prices', { params }),
        axios.get('http://localhost:5000/api/change-point', { params }),
        axios.get('http://localhost:5000/api/events', { params }),
        axios.get('http://localhost:5000/api/stats', { params }),
      ]);

      // Access nested 'data' consistently
      setData(pricesRes.data.data ?? []);
      setChangePoint(changePointRes.data.data ?? null); // Adjust based on actual response structure
      setEvents(eventsRes.data.data ?? []);
      setStats(statsRes.data.data ?? {});

    } catch (err) {
      const message = err.response?.data?.message || err.message || 'Failed to fetch data. Please try again.';
      setError(`❌ ${message}`);
      console.error('Fetch error:', err.response?.status, err.response?.data);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Container style={{ paddingTop: '2rem', paddingBottom: '2rem' }}>
      <div className="text-center mb-4">
        <h1>📈 Brent Oil Price Dashboard</h1>
        <p className="text-muted">Visualizing oil market behavior around global events</p>
      </div>

      <Row className="mb-4 justify-content-center">
        <Col xs="auto">
          <Form.Label>Start Date</Form.Label>
          <DatePicker
            selected={start}
            onChange={setStart}
            isClearable
            className="form-control"
            placeholderText="Select start"
            maxDate={end || new Date()}
          />
        </Col>
        <Col xs="auto">
          <Form.Label>End Date</Form.Label>
          <DatePicker
            selected={end}
            onChange={setEnd}
            isClearable
            className="form-control"
            placeholderText="Select end"
            minDate={start}
            maxDate={new Date()}
          />
        </Col>
        <Col xs="auto" className="d-flex align-items-end">
          <Button variant="primary" onClick={fetchData} disabled={loading}>
            {loading ? 'Applying...' : 'Apply Filters'}
          </Button>
        </Col>
      </Row>

      {loading && (
        <div className="text-center my-4">
          <Spinner animation="border" variant="primary" />
          <div>Loading data...</div>
        </div>
      )}

      {error && <Alert variant="danger">{error}</Alert>}

      {!loading && !error && (
        <>
          <Row className="mb-4">
            <Col md={6}>
              <StatCard title="📉 Volatility" value={stats.volatility?.toFixed(4)} />
            </Col>
            <Col md={6}>
              <StatCard title="📊 Avg Price Change" value={stats.average_change?.toFixed(4)} />
            </Col>
          </Row>

          <Card className="shadow">
            <Card.Body>
              <ChartComponent data={data} changePoint={changePoint} events={events} />
            </Card.Body>
          </Card>
        </>
      )}
    </Container>
  );
}

export default App;