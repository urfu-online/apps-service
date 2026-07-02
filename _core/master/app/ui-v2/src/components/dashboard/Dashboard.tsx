// Dashboard Component
import React from 'react';
import { Layout } from './layout/Layout';
import { useQuery } from '@tanstack/react-query';
import { Service } from '../lib/types';
import { api } from '../lib/api';

export const Dashboard: React.FC = () => {
  const {
    data: services,
    isLoading,
    isError,
    error
  } = useQuery<Service[]>({
    queryKey: ['services'],
    queryFn: getServices,
    staleTime: 5 * 60 * 1000, // 5 minutes
    cacheTime: 10 * 60 * 1000, // 10 minutes
  });

  if (isLoading) {
    return (
      <Layout>
        <div className="flex justify-center items-center h-64">
          <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
        </div>
      </Layout>
    );
  }

  if (isError) {
    return (
      <Layout>
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative" role="alert">
          <strong className="font-bold">Error! </strong>
          <span className="block sm:inline">{error instanceof Error ? error.message : 'Failed to load services'}</span>
        </div>
      </Layout>
    );
  }

  if (!services) {
    return (
      <Layout>
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative" role="alert">
          <strong className="font-bold">Error! </strong>
          <span className="block sm:inline">No services data available</span>
        </div>
      </Layout>
    );
  }

  const runningServices = services.filter(s => s.status === 'running').length;
  const stoppedServices = services.filter(s => s.status === 'stopped').length;
  const publicServices = services.filter(s => s.visibility === 'public').length;

  return (
    <Layout>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div className="bg-white p-6 rounded-lg shadow">
          <h3 className="text-lg font-medium text-gray-900">Total Services</h3>
          <p className="text-3xl font-bold mt-2">{services.length}</p>
        </div>
        <div className="bg-white p-6 rounded-lg shadow">
          <h3 className="text-lg font-medium text-green-700">Running</h3>
          <p className="text-3xl font-bold mt-2">{runningServices}</p>
        </div>
        <div className="bg-white p-6 rounded-lg shadow">
          <h3 className="text-lg font-medium text-red-700">Stopped</h3>
          <p className="text-3xl font-bold mt-2">{stoppedServices}</p>
        </div>
        <div className="bg-white p-6 rounded-lg shadow">
          <h3 className="text-lg font-medium text-blue-700">Public</h3>
          <p className="text-3xl font-bold mt-2">{publicServices}</p>
        </div>
      </div>

      <div className="bg-white shadow rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-xl font-semibold text-gray-800">Services</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Version</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Visibility</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Routing</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {services.map((service) => (
                <tr key={service.name}>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium text-gray-900">{service.display_name || service.name}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm text-gray-900">{service.version || '-'}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full 
                      ${service.visibility === 'public' ? 'bg-blue-100 text-blue-800' : 'bg-gray-100 text-gray-800'}`}>
                      {service.visibility}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full 
                      ${service.status === 'running' ? 'bg-green-100 text-green-800' : 
                        service.status === 'stopped' ? 'bg-red-100 text-red-800' : 
                        'bg-yellow-100 text-yellow-800'}`}>
                      {service.status === 'running' ? 'Running' : 
                       service.status === 'stopped' ? 'Stopped' : 'Partial'}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {service.routing?.map((route, index) => (
                      <div key={index}>
                        {route.type === 'domain' && `🌐 ${route.domain}`}
                        {route.type === 'port' && `🔌 :${route.port}`}
                        {route.type === 'subfolder' && `📁 ${route.base_domain}${route.path}`}
                      </div>
                    )) || '-'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                    <button className="text-blue-600 hover:text-blue-900 mr-3">View</button>
                    <button className="text-green-600 hover:text-green-900 mr-3">Restart</button>
                    <button className="text-red-600 hover:text-red-900">Stop</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Layout>
  );
};