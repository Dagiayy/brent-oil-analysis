import pymc as pm
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import arviz as az
import os

def run_change_point_analysis(data_path, output_dir='../outputs'):
    """
    Run Bayesian Change Point detection on Brent oil log returns.
    
    Parameters:
    -----------
    data_path : str
        Path to CSV file containing 'Date' and 'Log_Return' columns.
    output_dir : str
        Directory to save summary and plots.

    Returns:
    --------
    trace : arviz.InferenceData
        The trace of the sampling result.
    change_date : pd.Timestamp
        Estimated date of the change point.
    summary_df : pd.DataFrame
        Summary of posterior distributions.
    """
    # Create output directories if needed
    os.makedirs(os.path.join(output_dir, 'figures'), exist_ok=True)
    os.makedirs(os.path.join(output_dir, 'logs'), exist_ok=True)

    # Load and prepare data
    df = pd.read_csv(data_path, parse_dates=['Date'])
    df.dropna(inplace=True)
    returns = df['Log_Return'].values
    n = len(returns)

    # Define model
    with pm.Model() as model:
        tau = pm.DiscreteUniform('tau', lower=0, upper=n)
        mu1 = pm.Normal('mu1', mu=0, sigma=1)
        mu2 = pm.Normal('mu2', mu=0, sigma=1)
        sigma = pm.HalfNormal('sigma', sigma=1)
        mu = pm.math.switch(tau >= np.arange(n), mu1, mu2)
        obs = pm.Normal('obs', mu=mu, sigma=sigma, observed=returns)
        trace = pm.sample(2000, tune=1000, target_accept=0.95, return_inferencedata=True)

    # Summary & save
    summary_df = az.summary(trace, var_names=['mu1', 'mu2', 'tau', 'sigma'])
    summary_df.to_csv(os.path.join(output_dir, 'logs', 'trace_summary.csv'))

    # Plot trace
    az.plot_trace(trace, var_names=['mu1', 'mu2', 'tau', 'sigma'])
    plt.savefig(os.path.join(output_dir, 'figures', 'change_point_traceplot.png'))
    plt.close()

    # Posterior distributions for mu1 and mu2
    mu1_samples = trace.posterior['mu1'].values.flatten()
    mu2_samples = trace.posterior['mu2'].values.flatten()

    plt.figure(figsize=(10,6))
    plt.hist(mu1_samples, bins=50, alpha=0.5, label='mu1 (before)', color='skyblue')
    plt.hist(mu2_samples, bins=50, alpha=0.5, label='mu2 (after)', color='orange')
    plt.axvline(mu1_samples.mean(), color='blue', linestyle='--')
    plt.axvline(mu2_samples.mean(), color='red', linestyle='--')
    plt.legend()
    plt.title('Posterior Distributions of Mean Log Returns')
    plt.xlabel('Mean Log Return')
    plt.ylabel('Frequency')
    plt.savefig(os.path.join(output_dir, 'figures', 'posterior_mu_comparison.png'))
    plt.close()

    # Identify most probable change date
    most_probable_tau = int(trace.posterior['tau'].values[0].mean())
    change_date = df.iloc[most_probable_tau]['Date']

    return trace, change_date, summary_df

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Run Bayesian Change Point Detection on Brent Oil log returns.')
    parser.add_argument('--data', type=str, default='../data/processed/brent_log_returns.csv', help='Path to input CSV data')
    parser.add_argument('--output', type=str, default='../outputs', help='Directory to save outputs')
    args = parser.parse_args()

    trace, change_date, summary = run_change_point_analysis(args.data, args.output)
    print(f"Most probable change point date: {change_date.date()}")
    print(summary)
