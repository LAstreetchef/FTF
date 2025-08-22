# Squarespace Embed Instructions

## How to Add the Food Truck Fundraiser to Your Squarespace Site

### Step 1: Copy the Embed Code
1. Open `squarespace_embed_code.html` 
2. Copy the entire contents of the file (Ctrl+A, then Ctrl+C)

### Step 2: Add to Squarespace
1. Log into your Squarespace admin panel
2. Navigate to the page where you want to add the fundraiser
3. Click the **"+"** button to add a new content block
4. Select **"Code"** from the content block options
5. Paste the copied code into the code block
6. Click **"Apply"** to save

### Step 3: Verify the Integration
1. Preview or publish your page
2. The fundraiser should load in an iframe
3. Test that login and navigation work properly

## Features Included

✅ **Responsive Design**: Automatically adjusts to different screen sizes  
✅ **Loading Indicator**: Shows a spinner while the app loads  
✅ **Error Handling**: Displays helpful error messages if loading fails  
✅ **Security**: Proper iframe sandboxing and origin validation  
✅ **Dynamic Height**: Can adjust iframe height based on content  

## Customization Options

### Change the Height
Edit this line in the code:
```css
height: 800px;  /* Change this value */
```

### Modify Colors
Update the loading spinner color:
```css
border-top: 4px solid #ff6b35;  /* Change this color */
```

### Update Domain
If you deploy to a custom domain, update this line:
```javascript
if (event.origin !== 'https://YOUR-NEW-DOMAIN.com') {
```

## Troubleshooting

**Issue**: Iframe doesn't load
- **Solution**: Check that the Replit app is running and accessible

**Issue**: Login doesn't work in iframe
- **Solution**: The auth token system should handle this automatically

**Issue**: Content is cut off
- **Solution**: Increase the iframe height in the CSS

**Issue**: Mobile display issues
- **Solution**: The responsive CSS should handle this, but you can adjust the mobile heights

## Support

If you encounter any issues:
1. Check the browser console for error messages
2. Verify the Replit app URL is correct and accessible
3. Ensure Squarespace allows iframe embedding (it should by default)

The embed code includes comprehensive error handling and should work seamlessly with Squarespace's platform.