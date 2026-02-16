import React from 'react';
import './PreviewPanel.css';

// Helper function to truncate large objects before stringifying
const truncateObject = (obj, maxDepth = 3, currentDepth = 0) => {
  if (currentDepth >= maxDepth) {
    return '[Truncated]';
  }
  
  if (Array.isArray(obj)) {
    // Limit arrays to first 10 items
    const truncated = obj.slice(0, 10).map(item => 
      typeof item === 'object' && item !== null 
        ? truncateObject(item, maxDepth, currentDepth + 1)
        : item
    );
    if (obj.length > 10) {
      truncated.push(`... (${obj.length - 10} more items)`);
    }
    return truncated;
  }
  
  if (typeof obj === 'object' && obj !== null) {
    const truncated = {};
    const keys = Object.keys(obj);
    // Limit to first 20 keys
    const keysToShow = keys.slice(0, 20);
    for (const key of keysToShow) {
      const value = obj[key];
      truncated[key] = typeof value === 'object' && value !== null
        ? truncateObject(value, maxDepth, currentDepth + 1)
        : value;
    }
    if (keys.length > 20) {
      truncated['...'] = `${keys.length - 20} more keys`;
    }
    return truncated;
  }
  
  return obj;
};

const PreviewPanel = ({ fileContent, fileName, sampleRows = 5 }) => {
  if (!fileContent) {
    return (
      <div className="preview-panel">
        <p className="preview-empty">No file uploaded yet</p>
      </div>
    );
  }

  // Handle different file content formats
  let displayContent = fileContent;
  let rows = [];
  let totalLines = 0;
  let isTruncated = false;

  if (typeof fileContent === 'string') {
    // Try to parse as JSON if it looks like JSON (for .json files)
    const isJsonFile = fileName.toLowerCase().endsWith('.json');
    if (isJsonFile) {
      try {
        const parsed = JSON.parse(fileContent);
        // If parsing succeeds, treat as object/array for better preview
        if (typeof parsed === 'object' && parsed !== null) {
          const truncated = truncateObject(parsed);
          displayContent = JSON.stringify(truncated, null, 2);
          const allRows = displayContent.split('\n');
          totalLines = allRows.length;
          rows = allRows.slice(0, sampleRows);
        } else {
          // If parsed to primitive, treat as string
          const allRows = fileContent.split('\n');
          totalLines = allRows.length;
          rows = allRows.slice(0, sampleRows);
        }
      } catch {
        // If JSON parsing fails, treat as regular string
        const maxChars = 100000; // 100KB max
        if (fileContent.length > maxChars) {
          displayContent = fileContent.substring(0, maxChars) + '\n\n... (content truncated)';
          isTruncated = true;
        }
        const allRows = displayContent.split('\n');
        totalLines = allRows.length;
        rows = allRows.slice(0, sampleRows);
      }
    } else {
      // For non-JSON files, limit string processing to prevent freezing
      const maxChars = 100000; // 100KB max
      if (fileContent.length > maxChars) {
        displayContent = fileContent.substring(0, maxChars) + '\n\n... (content truncated)';
        isTruncated = true;
      }
      const allRows = displayContent.split('\n');
      totalLines = allRows.length;
      rows = allRows.slice(0, sampleRows);
    }
  } else if (Array.isArray(fileContent)) {
    totalLines = fileContent.length;
    rows = fileContent.slice(0, sampleRows);
  } else if (typeof fileContent === 'object') {
    // Truncate large objects before stringifying to prevent freezing
    const truncated = truncateObject(fileContent);
    displayContent = JSON.stringify(truncated, null, 2);
    const allRows = displayContent.split('\n');
    totalLines = allRows.length;
    rows = allRows.slice(0, sampleRows);
  }

  return (
    <div className="preview-panel">
      <div className="preview-header">
        <h3>File Preview: {fileName}</h3>
        <span className="preview-info">
          Showing first {rows.length} {rows.length === 1 ? 'line' : 'lines'}
          {totalLines > sampleRows && ` of ${totalLines}`}
        </span>
      </div>
      <div className="preview-content">
        <pre>{rows.join('\n')}</pre>
        {(totalLines > sampleRows || isTruncated) && (
          <p className="preview-more">
            {isTruncated 
              ? '... (preview truncated for performance)'
              : `... and ${totalLines - sampleRows} more ${totalLines - sampleRows === 1 ? 'line' : 'lines'}`
            }
          </p>
        )}
      </div>
    </div>
  );
};

export default PreviewPanel;
