import React from 'react';
import {
  Chart as ChartJS,
  LineElement,
  CategoryScale,
  LinearScale,
  PointElement,
  TimeScale,
  Tooltip,
  Legend,
} from 'chart.js';

import annotationPlugin from 'chartjs-plugin-annotation';
import 'chartjs-adapter-date-fns';
import { Line } from 'react-chartjs-2';

ChartJS.register(
  LineElement,
  PointElement,
  CategoryScale,
  LinearScale,
  TimeScale,
  Tooltip,
  Legend,
  annotationPlugin
);

const ChartComponent = ({ data, changePoint, events }) => {
  const chartData = {
    labels: data.map((d) => d.Date),
    datasets: [
      {
        label: 'Log Return',
        data: data.map((d) => d.Log_Return),
        borderColor: 'blue',
        backgroundColor: 'rgba(0, 0, 255, 0.2)',
        pointRadius: 0,
        fill: false,
        tension: 0.1,
      },
    ],
  };

  const annotations = changePoint
    ? {
        cpLine: {
          type: 'line',
          xMin: changePoint.change_date,
          xMax: changePoint.change_date,
          borderColor: 'red',
          borderWidth: 2,
          label: {
            content: 'Change Point',
            enabled: true,
            position: 'start',
            backgroundColor: 'rgba(255, 0, 0, 0.7)',
          },
        },
      }
    : {};

  const options = {
    responsive: true,
    plugins: {
      legend: { display: true },
      tooltip: {
        callbacks: {
          afterBody: (context) => {
            const label = context[0].label;
            const e = events.find((ev) => ev['Start Date'] === label);
            return e ? `Event: ${e.Event}` : null;
          },
        },
      },
      annotation: {
        annotations: annotations,
      },
    },
    scales: {
      x: {
        type: 'time',
        time: {
          unit: 'month',
          tooltipFormat: 'yyyy-MM-dd',
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
  };

  return (
    <div style={{ backgroundColor: '#fff', padding: '1rem', borderRadius: '8px' }}>
      <h3 style={{ textAlign: 'center' }}>Brent Oil Log Returns</h3>
      <Line data={chartData} options={options} />
    </div>
  );
};

export default ChartComponent;
