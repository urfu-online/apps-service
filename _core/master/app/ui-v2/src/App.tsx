// Main App component
import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import { queryClient } from './lib/api';
import { Dashboard } from './components/dashboard/Dashboard';
import { Services } from './components/services/Services';
import { Logs } from './components/logs/Logs';
import { Backups } from './components/backups/Backups';
import { Layout } from './components/layout/Layout';

const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <Router>
        <div className="min-h-screen bg-gray-100">
          <Routes>
            <Route path="/" element={
              <Layout>
                <Dashboard />
              </Layout>
            } />
            <Route path="/services" element={
              <Layout>
                <Services />
              </Layout>
            } />
            <Route path="/logs" element={
              <Layout>
                <Logs />
              </Layout>
            } />
            <Route path="/backups" element={
              <Layout>
                <Backups />
              </Layout>
            } />
            <Route path="/login" element={<div className="min-h-screen bg-gray-100 flex items-center justify-center">
              <div className="bg-white p-8 rounded-lg shadow-md w-96">
                <h2 className="text-2xl font-bold mb-6 text-center">Login</h2>
                <form>
                  <div className="mb-4">
                    <label className="block text-gray-700 text-sm font-bold mb-2" htmlFor="username">
                      Username
                    </label>
                    <input
                      id="username"
                      type="text"
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="Enter your username"
                    />
                  </div>
                  <div className="mb-6">
                    <label className="block text-gray-700 text-sm font-bold mb-2" htmlFor="password">
                      Password
                    </label>
                    <input
                      id="password"
                      type="password"
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="Enter your password"
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <button
                      type="button"
                      className="w-full bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                      onClick={() => {
                        // TODO: Implement actual authentication
                        alert('Authentication functionality would be implemented here');
                      }}
                    >
                      Sign In
                    </button>
                  </div>
                </form>
              </div>
            </div>} />
          </Routes>
        </div>
      </Router>
    </QueryClientProvider>
  );
};

export default App;