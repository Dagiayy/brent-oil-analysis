import React from 'react';
import {
  Chart as ChartJS,
  TimeScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
} from 'chart.js';
import annotationPlugin from 'chartjs-plugin-annotation';
import 'chartjs-adapter-date-fns';
import { Line } from 'react-chartjs-2';

ChartJS.register(TimeScale, LinearScale, PointElement, LineElement, Tooltip, Legend, annotationPlugin);

const ChartComponent = ({ data, changePoint, events }) => {
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

  const annotations = changePoint && changePoint.change_date
    ? {
        changePointLine: {
          type: 'line',
          scaleID: 'x',
          value: new Date(changePoint.change_date),
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
        time: { unit: 'month' },
        title: { display: true, text: 'Date' },
      },
      y: {
        title: { display: true, text: 'Log Return' },
      },
    },
    plugins: {
      annotation: { annotations },
      tooltip: {
        callbacks: {
          afterBody: (ctx) => {
            const labelDate = new Date(ctx[0].label).setHours(0, 0, 0, 0);
            const event = (events || []).find((ev) => {
              const eventDate = new Date(ev['Start Date']).setHours(0, 0, 0, 0);
              return eventDate === labelDate;
            });
            return event ? `Event: ${event.Event}` : '';
          },
        },
      },
      legend: { display: true, position: 'top' },
    },
  };

  return <Line data={chartData} options={options} />;
};

export default ChartComponent;
